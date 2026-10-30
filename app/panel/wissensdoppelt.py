"""Doppelte Punkte der Wissenskarte (plan wissensgraph, Nachtrag zu Stufe 2, Dominik 2026-10-30 „ok nach Empfehlung
umsetzen“): the people, companies, places, contracts, accounts and deadlines of the documents (wissenskarte.py, wk_ent)
come in many spellings („Herr Dominik Bornhäuser“, „Bornhäuser, Dominik“, „Dominik Bornhäuser“). Fixed rules decide
which two are the same, never the model:

- aehnlich(art, a, b) -> (stufe, grund) is the one rule: stufe "gleich" (the same point), "vorschlag" (maybe the same:
  the owner decides) or None, grund one fixed word of GRUENDE. Every name is compared in its normal form per kind
  (normalform): ß/ss, ä/ae, ö/oe, ü/ue, accents, signs and spaces never count; people without a form of address or a
  title (ANREDEN) and „Nachname, Vorname“ as „Vorname Nachname“; companies without a legal form (RECHTSFORMEN), without
  „Firma“ in front and with „&“ as „und“; places with „Str.“ as „Straße“ and „Pl.“ as „Platz“.
- "gleich" only for people and places whose names differ in nothing but a form of address, a title, the spelling or
  the order of first and last name (a person with first and last name; „Herr“ and „Frau“ never together), and for
  accounts (without spaces), contracts and deadlines with the same normal form. A company is never "gleich" by these
  rules: a legal form alone („Müller GmbH“, „Müller AG“) is only a "vorschlag".
- "vorschlag": a distance of at most 2 letters (Damerau-Levenshtein) between normal forms of at least 6 letters, 1 for 4
  to 5 letters; a person with an initial („D. Bornhäuser“), only when exactly one person fits; a company with the same
  core without legal form. Different numbers in two names are never the same; accounts, contracts and deadlines are
  never compared by typing errors.

What happens with it:
1. While points are read in (wissenskarte.apply_ents → _match → gleich_id), a new name that is "gleich" to a point
   there becomes an other name of that point instead of a point of its own.
2. In quiet minutes (wissen.due_once, after the map) lauf() merges points there that are "gleich" through
   wissenskarte.zusammen (the same function as the owner's click, so GEAENDERT says "zusammen") and fills wk_paar with
   suggestions by the rules above: compared only within blocks (first and last letters, last name, core of a
   company) and with neighbours of similar length, at most VERGLEICHE_MOST comparisons, LAUF_S seconds, PAARE_LAUF new
   suggestions per run and PAARE_MOST open per profile; it runs again only when the points changed, at most LAEUFE_TAG
   times a day per profile.
3. The owner sees them under Wissensbuch → Karte → „Vielleicht doppelt“ and at a chosen point („Vielleicht dieselbe
   Person: …“): „Zusammenführen“ goes through the endpoint of the click (code of „Bestätigen“, stufen.LIST),
   „Verschieden“ is kept by the names (stand "verschieden"), so the pair never comes back, also not automatically.
4. The list to merge with is a search field: the AEHNLICH_MOST most similar points of the same kind first (auswahl),
   the rest by search, at most TREFFER_MOST hits.

No switch of its own: it improves Personen, Firmen und Fristen (chat.knowledge_ents) and follows its release; guests
never. The journal gets fixed words and numbers only, Live only numbers (open suggestions, merged automatically).

    GET  /api/profile/wissenskarte/paare                    open suggestions („Vielleicht doppelt“)
    POST /api/profile/wissenskarte/paare/verschieden        {"a": id, "b": id}: the two are different, for good
    GET  /api/profile/wissenskarte/knoten/{kid}/aehnlich    suggestions of one point, its most similar, search (?q=)
"""
import asyncio
import datetime
import functools
import json
import os
import re
import time
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Request

import documents
import guard
import profiles
import wissenskarte as wk
from core import assistant, browser_profile, json_body, own_profile

router = APIRouter()
STUFEN = ("gleich", "vorschlag")
GRUENDE = ("schreibweise", "anrede", "reihenfolge", "initiale", "rechtsform", "tippfehler")
GLEICH_ARTEN = ("person", "ort")                 # the same by spelling, address and order: merged by itself
NUR_GLEICH = ("konto", "vertrag", "frist")       # never by typing errors, only the same normal form
TIPP_ARTEN = ("person", "firma", "ort")          # compared by typing errors (suggestions)
AEHNLICH_MOST = 8        # most similar points of the same kind at the top of „Zusammenführen mit …“
TREFFER_MOST = 20        # hits of the search below them
PAARE_ZEIGEN = 50        # open suggestions one answer shows
PAARE_LAUF = 100         # new suggestions one run brings per profile
PAARE_MOST = 300         # open suggestions per profile
AUTO_LAUF = 200          # points one run merges by itself per profile
VERGLEICHE_MOST = 200000  # pairs one run compares per profile
NACHBARN_MOST = 40       # neighbours (by length) one point is compared with in a block
LAUF_S = 3.0             # seconds one run may take per profile
LAEUFE_TAG = 6           # runs per profile and day (only when the points changed)
VERSCHIEDEN_MOST = 5000  # pairs kept as „Verschieden“ per profile (the oldest go first)
_GRUND_RANG = {g: i for i, g in enumerate(GRUENDE)}
SCHEMA = (
    "CREATE TABLE IF NOT EXISTS wk_paar (a INTEGER NOT NULL, b INTEGER NOT NULL, art TEXT NOT NULL, grund TEXT NOT NULL, "
    "stand TEXT NOT NULL, na TEXT NOT NULL, nb TEXT NOT NULL, at INTEGER, PRIMARY KEY (a, b))",
    "CREATE INDEX IF NOT EXISTS wk_paar_nein ON wk_paar(stand, art)",
    "CREATE TABLE IF NOT EXISTS wk_entkey (ent INTEGER NOT NULL, art TEXT NOT NULL, key TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS wk_entkey_key ON wk_entkey(art, key)",
    "CREATE INDEX IF NOT EXISTS wk_entkey_ent ON wk_entkey(ent)",
    "CREATE TABLE IF NOT EXISTS wk_entsig (ent INTEGER PRIMARY KEY, sig TEXT NOT NULL)",
)
TABELLEN = ("wk_paar", "wk_entkey", "wk_entsig")
ZAHLEN = {"auto": 0, "einlesen": 0, "verschieden": 0}   # Live-Übersicht: since the start, in the memory only
_busy = set()
_sig = {}
_live = {"at": 0.0, "d": None}
LIVE_CACHE = 20


def tabellen(con):
    """The tables of this module in the profile's wissen.db (con.execute, so an open transaction stays open)."""
    for s in SCHEMA:
        con.execute(s)


class _Db(wk._Db):
    def __enter__(self):
        con = super().__enter__()
        try:
            tabellen(con)
        except BaseException:
            self.__exit__(Exception)
            raise
        return con


# ---------------------------------------------------------------- the normal form per kind (one source)
_FALTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "Ä": "ae", "Ö": "oe", "Ü": "ue", "ẞ": "ss"})


def falte(text):
    """A text as names are compared: ß/ss, ä/ae, ö/oe, ü/ue, without accents, lower case, „&“ as „und“, „e. V.“ as
    „ev“, signs as spaces, spaces drawn together."""
    s = unicodedata.normalize("NFKD", str(text or "").translate(_FALTE))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().replace("&", " und ")
    s = re.sub(r"\b([a-z])\.\s?([a-z])\b\.?", r"\1\2", s)
    return re.sub(r"\s+", " ", re.sub(r"[\W_]+", " ", s)).strip()


_ANREDEN = frozenset(t for w in wk.ANREDEN for t in falte(w).split())
_RECHTSFORMEN = frozenset(t for w in wk.RECHTSFORMEN for t in falte(w).split())
_MANN, _FRAU = frozenset(("herr", "hr", "mr")), frozenset(("frau", "fr", "mrs", "ms"))
_ORT = {"str": "strasse", "pl": "platz"}


@functools.lru_cache(maxsize=20000)
def normalform(art, name):
    """(tokens, Vergleichstext, Zahlen, Geschlecht, Kern, umgestellt, Anrede weg) of a name of this kind: the fixed
    normal form every rule compares (Vergleichstext without spaces; Kern: a company without legal form)."""
    raw = str(name or "")
    umgestellt = False
    if art == "person" and raw.count(",") == 1:      # „Nachname, Vorname“ → „Vorname Nachname“
        last, first = (x.strip() for x in raw.split(","))
        if last and first:
            raw, umgestellt = first + " " + last, True
    toks = falte(raw).split()
    sex, weg = "", False
    if art == "person":
        while len(toks) > 1 and toks[0] in _ANREDEN:
            sex = sex or ("m" if toks[0] in _MANN else "w" if toks[0] in _FRAU else "")
            toks, weg = toks[1:], True
    elif art == "firma" and len(toks) > 1 and toks[0] == "firma":
        toks = toks[1:]
    elif art == "ort":
        toks = [_ORT.get(t, t[:-3] + "strasse" if len(t) > 3 and t.endswith("str") else t) for t in toks]
    kern = list(toks)
    if art == "firma":
        while len(kern) > 1 and (kern[-1] in _RECHTSFORMEN or kern[-1] == "und"):
            kern.pop()
        if kern and kern[-1] in _RECHTSFORMEN:
            kern = []
    return (tuple(toks), "".join(toks), tuple(re.findall(r"\d+", " ".join(toks))), sex, " ".join(kern), umgestellt, weg)


def schluessel(art, name):
    """The key of a name for "gleich" (the index wk_entkey): the same key is necessary, aehnlich decides; "" for a
    kind or a name that is never "gleich" by these rules (companies; a person with one word)."""
    if art == "konto":
        return wk._compact(name)
    if art not in GLEICH_ARTEN + NUR_GLEICH:
        return ""
    toks = normalform(art, name)[0]
    if art == "person" and len(toks) < 2:
        return ""
    return " ".join(toks)


def abstand(x, y, most):
    """Damerau-Levenshtein distance (neighbouring letters swapped count once) of two texts, or most + 1 as soon as it
    is surely larger than most (only a band of the table is worked out)."""
    if abs(len(x) - len(y)) > most:
        return most + 1
    if x == y:
        return 0
    prev2, prev = None, list(range(len(y) + 1))
    for i in range(1, len(x) + 1):
        cur = [i] + [most + 1] * len(y)
        lo, hi = max(1, i - most), min(len(y), i + most)
        for j in range(lo, hi + 1):
            cost = 0 if x[i - 1] == y[j - 1] else 1
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if prev2 is not None and i > 1 and j > 1 and x[i - 1] == y[j - 2] and x[i - 2] == y[j - 1]:
                v = min(v, prev2[j - 2] + 1)
            cur[j] = v
        if min(cur[lo - 1:hi + 1]) > most:
            return most + 1
        prev2, prev = prev, cur
    return min(prev[len(y)], most + 1)


def grenze(n):
    """The largest distance that is still a suggestion for a normal form of n letters (0: none)."""
    return 2 if n >= 6 else 1 if n >= 4 else 0


def _initiale(ta, tb):
    """Whether two people differ only by initials („D. Bornhäuser“, „Dominik Bornhäuser“): same last name, every other
    word the same or one letter that begins the other, at least one such letter."""
    if len(ta) != len(tb) or len(ta) < 2 or ta[-1] != tb[-1]:
        return False
    one = False
    for x, y in zip(ta[:-1], tb[:-1]):
        if x == y:
            continue
        if len(x) == 1 and y.startswith(x) or len(y) == 1 and x.startswith(y):
            one = True
            continue
        return False
    return one


def aehnlich(art, a, b):
    """The one rule: ("gleich" | "vorschlag" | None, grund) for two names of points of the kind art (see the module)."""
    if art not in wk.ENT_ARTEN or not str(a or "").strip() or not str(b or "").strip():
        return None, ""
    if wk.ent_norm(a) == wk.ent_norm(b):
        return "gleich", "schreibweise"
    if art == "konto":
        return ("gleich", "schreibweise") if wk._compact(a) == wk._compact(b) else (None, "")
    na, nb = normalform(art, a), normalform(art, b)
    if art in NUR_GLEICH:
        return ("gleich", "schreibweise") if na[0] == nb[0] else (None, "")
    if na[2] != nb[2]:
        return None, ""                                  # different numbers are never the same
    if art == "person":
        if na[3] and nb[3] and na[3] != nb[3]:
            return None, ""                              # „Herr“ and „Frau“ never together
        if na[0] == nb[0]:
            grund = ("anrede" if na[6] or nb[6] else "reihenfolge" if na[5] or nb[5] else "schreibweise")
            return ("gleich" if len(na[0]) >= 2 else "vorschlag"), grund
        if _initiale(na[0], nb[0]):
            return "vorschlag", "initiale"
    elif art == "ort" and na[0] == nb[0]:
        return "gleich", "schreibweise"
    elif art == "firma":
        if na[0] == nb[0]:
            return "vorschlag", "schreibweise"
        if na[4] and na[4] == nb[4]:
            return "vorschlag", "rechtsform"
    x, y = (na[4].replace(" ", ""), nb[4].replace(" ", "")) if art == "firma" else (na[1], nb[1])
    most = grenze(min(len(x), len(y)))
    if most and x and y and abstand(x, y, most) <= most:
        return "vorschlag", "schreibweise" if x == y else "tippfehler"
    return None, ""


# ---------------------------------------------------------------- the index of keys and „Verschieden“
def _namen(row):
    return [row["name"]] + wk._aliases(row["alias"])


def auffrischen(con, art=None):
    """Brings wk_entkey up to the points there: a point whose name or other names changed (or that is new) gets its
    keys again (fingerprint in wk_entsig); keys of points that went are only ever read through a join with wk_ent."""
    q = ("SELECT e.id, e.art, e.name, e.alias FROM wk_ent e LEFT JOIN wk_entsig s ON s.ent = e.id "
         "WHERE (s.sig IS NULL OR s.sig <> e.name || char(31) || e.alias)" + (" AND e.art = ?" if art else ""))
    rows = con.execute(q, (art,) if art else ()).fetchall()
    for r in rows:
        con.execute("DELETE FROM wk_entkey WHERE ent=?", (r["id"],))
        keys = {k for k in (schluessel(r["art"], n) for n in _namen(r)) if k}
        con.executemany("INSERT INTO wk_entkey (ent, art, key) VALUES (?, ?, ?)", [(r["id"], r["art"], k) for k in sorted(keys)])
        con.execute("INSERT OR REPLACE INTO wk_entsig (ent, sig) VALUES (?, ?)", (r["id"], r["name"] + "\x1f" + r["alias"]))
    return len(rows)


def _nein(con):
    """{(art, name, name)} of the pairs the owner called different (names as ent_norm writes them, sorted)."""
    return {(r[0], *sorted((r[1], r[2]))) for r in con.execute("SELECT art, na, nb FROM wk_paar WHERE stand='verschieden'")}


def _verschieden(nein, art, names_a, names_b):
    na = {wk.ent_norm(x) for x in names_a}
    nb = {wk.ent_norm(x) for x in names_b}
    return any((art, *sorted((x, y))) in nein for x in na for y in nb)


def _gleich(art, names_a, names_b):
    return next((g for x in names_a for y in names_b for s, g in [aehnlich(art, x, y)] if s == "gleich"), "")


def gleich_id(con, art, name):
    """wissenskarte._match: the point there whose name or other name is "gleich" to this new name (never one the
    owner called different from it), with the name added as other name; else None. Fixed rules only."""
    tabellen(con)
    key = schluessel(art, name)
    if not key:
        return None
    auffrischen(con, art)
    nein = _nein(con)
    for r in con.execute("SELECT e.id, e.art, e.name, e.alias FROM wk_entkey k JOIN wk_ent e ON e.id = k.ent "
                         "WHERE k.art=? AND k.key=? GROUP BY e.id ORDER BY e.id", (art, key)).fetchall():
        names = _namen(r)
        grund = _gleich(art, [name], names)
        if not grund or _verschieden(nein, art, [name], names):
            continue
        al = wk._aliases(r["alias"])
        if wk.ent_norm(name) not in {wk.ent_norm(x) for x in names} and len(al) < wk.ALIAS_MOST:
            con.execute("UPDATE wk_ent SET alias=? WHERE id=?", (json.dumps(al + [name], ensure_ascii=False), r["id"]))
        ZAHLEN["einlesen"] += 1
        print(f"wissen: wissenskarte doppelt einlesen | 1 knoten | {grund}", flush=True)
        return r["id"]
    return None


def leeren(con):
    """Ich → Daten löschen (wissenskarte._ent_clear): the suggestions, „Verschieden“ and the keys go too."""
    tabellen(con)
    for t in TABELLEN:
        con.execute(f"DELETE FROM {t}")


# ---------------------------------------------------------------- the quiet run
def _bloecke(art, rows):
    """{block: [ids]}: points that may be compared (the same first or last three letters, the same last name, the
    same core of a company); never all with all."""
    out = {}
    for i, name in rows:
        nf = normalform(art, name)
        keys = []
        if len(nf[1]) >= 4:
            keys += [("a", nf[1][:3]), ("z", nf[1][-3:])]
        if art == "person" and len(nf[0]) >= 2:
            keys.append(("n", nf[0][-1]))
        if art == "firma" and nf[4]:
            keys.append(("k", nf[4]))
        for k in keys:
            out.setdefault(k, []).append(i)
    return out


def _vergleiche(art, rows, c, t0, budget):
    """The pairs („vorschlag“) of one kind, compared in blocks and with neighbours of similar length: {(a, b): grund}."""
    name = dict(rows)
    found, initial, seen = {}, {}, set()
    for key, ids in sorted(_bloecke(art, rows).items()):
        ids = sorted(ids, key=lambda i: (len(normalform(art, name[i])[1]), i))
        for x, i in enumerate(ids):
            for j in ids[x + 1:x + 1 + NACHBARN_MOST]:
                if key[0] in ("a", "z") and len(normalform(art, name[j])[1]) - len(normalform(art, name[i])[1]) > 2:
                    break
                p = (min(i, j), max(i, j))
                if p in seen:
                    continue
                seen.add(p)
                c["vergleiche"] += 1
                if c["vergleiche"] >= VERGLEICHE_MOST or c["vergleiche"] % 500 == 0 and time.monotonic() - t0 > budget:
                    c["fertig"] = False
                    return found, initial
                s, g = aehnlich(art, name[p[0]], name[p[1]])
                if s != "vorschlag":
                    continue
                if g == "initiale":       # only when exactly one person fits the one with the initial
                    for x1, x2 in (p, p[::-1]):
                        if any(len(t) == 1 for t in normalform(art, name[x1])[0][:-1]):
                            initial.setdefault(x1, set()).add(x2)
                else:
                    found[p] = g
    return found, initial


def lauf(uid, now=None, budget=LAUF_S):
    """One run for one profile: merges what is "gleich" (through wissenskarte.zusammen) and finds suggestions. Returns
    the counts {"auto", "neu", "offen", "weg", "vergleiche", "fertig"}."""
    t0 = time.monotonic()
    now = int(now or time.time())
    c = {"auto": 0, "neu": 0, "offen": 0, "weg": 0, "vergleiche": 0, "fertig": True}
    with _Db(uid) as con:
        auffrischen(con)
        con.execute("DELETE FROM wk_entkey WHERE ent NOT IN (SELECT id FROM wk_ent)")
        con.execute("DELETE FROM wk_entsig WHERE ent NOT IN (SELECT id FROM wk_ent)")
        rows = {r["id"]: r for r in con.execute("SELECT id, art, name, alias FROM wk_ent ORDER BY id")}
        nein = _nein(con)
        merges = []
        for r in con.execute("SELECT k.art, GROUP_CONCAT(DISTINCT k.ent) AS ids FROM wk_entkey k JOIN wk_ent e ON "
                             "e.id = k.ent GROUP BY k.art, k.key HAVING COUNT(DISTINCT k.ent) > 1 ORDER BY MIN(k.ent)"):
            ids = sorted(int(x) for x in r["ids"].split(","))
            for o in ids[1:]:
                a, b = rows[ids[0]], rows[o]
                if _gleich(r["art"], _namen(a), _namen(b)) and not _verschieden(nein, r["art"], _namen(a), _namen(b)):
                    merges.append((o, ids[0]))
    into = {}
    for o, t in merges[:AUTO_LAUF]:
        while t in into:                      # the target went into another point already
            t = into[t]
        if o == t or o in into:
            continue
        if wk.zusammen(uid, o, t) == "ok":     # the same function as the owner's click: GEAENDERT says "zusammen"
            into[o] = t
            c["auto"] += 1
    if len(merges) > AUTO_LAUF:
        c["fertig"] = False
    ZAHLEN["auto"] += c["auto"]
    with _Db(uid) as con:
        c["weg"] = con.execute("DELETE FROM wk_paar WHERE stand='offen' AND (a NOT IN (SELECT id FROM wk_ent) OR "
                               "b NOT IN (SELECT id FROM wk_ent))").rowcount
        rows = {r["id"]: r for r in con.execute("SELECT id, art, name, alias FROM wk_ent ORDER BY id")}
        for p in con.execute("SELECT a, b, art FROM wk_paar WHERE stand='offen'").fetchall():   # renamed since
            if aehnlich(p["art"], rows[p["a"]]["name"], rows[p["b"]]["name"])[0] != "vorschlag":
                c["weg"] += con.execute("DELETE FROM wk_paar WHERE a=? AND b=?", (p["a"], p["b"])).rowcount
        have = {(r[0], r[1]) for r in con.execute("SELECT a, b FROM wk_paar")}
        offen = con.execute("SELECT COUNT(*) FROM wk_paar WHERE stand='offen'").fetchone()[0]
        found = {}
        for art in TIPP_ARTEN:
            got, initial = _vergleiche(art, [(i, r["name"]) for i, r in rows.items() if r["art"] == art], c, t0, budget)
            found.update(got)
            for i, others in initial.items():
                if len(others) == 1:
                    j = next(iter(others))
                    found.setdefault((min(i, j), max(i, j)), "initiale")
            if not c["fertig"]:
                break
        for (a, b), g in sorted(found.items(), key=lambda x: (_GRUND_RANG[x[1]], x[0])):
            if (a, b) in have or _verschieden(nein, rows[a]["art"], _namen(rows[a]), _namen(rows[b])):
                continue
            if c["neu"] >= PAARE_LAUF or offen >= PAARE_MOST:
                c["fertig"] = c["fertig"] and offen >= PAARE_MOST
                break
            con.execute("INSERT INTO wk_paar (a, b, art, grund, stand, na, nb, at) VALUES (?, ?, ?, ?, 'offen', ?, ?, ?)",
                        (a, b, rows[a]["art"], g, wk.ent_norm(rows[a]["name"]), wk.ent_norm(rows[b]["name"]), now))
            c["neu"] += 1
            offen += 1
        c["offen"] = offen
    return c


def _stand(uid):
    """What a run depends on: the points, their names and „Verschieden“ (a fingerprint, numbers only)."""
    with _Db(uid) as con:
        r = con.execute("SELECT COUNT(*), COALESCE(MAX(id), 0), COALESCE(SUM(LENGTH(name) + LENGTH(alias)), 0) "
                        "FROM wk_ent").fetchone()
        n = con.execute("SELECT COUNT(*) FROM wk_paar WHERE stand='verschieden'").fetchone()[0]
    return (r[0], r[1], r[2], n)


async def due_once(now=None):
    """One step of quiet work (wissen.due_once, after the map): one run for one profile whose points changed since its
    last run, at most LAEUFE_TAG a day. Returns "wissensdoppelt" when it ran, else None."""
    if not wk.ents_on():
        return None
    now = now or time.time()
    day = datetime.datetime.fromtimestamp(now).strftime("%Y-%m-%d")
    for uid in profiles.user_ids():
        if uid in _busy or not wk.ents_allowed(uid) or not os.path.exists(documents.db_path(uid)):
            continue
        sig = await asyncio.to_thread(_stand, uid)
        if not sig[0] or _sig.get(uid) == sig or documents.count_today(uid, day, key="wkdoppelt") >= LAEUFE_TAG:
            continue
        documents.count_today(uid, day, add=1, key="wkdoppelt")
        _busy.add(uid)
        t0 = time.time()
        try:
            c = await asyncio.to_thread(lauf, uid, now)
        except Exception as e:     # noqa: BLE001
            print("wissen: wissenskarte doppelt fehler |", type(e).__name__, flush=True)
            return "wissensdoppelt"
        finally:
            _busy.discard(uid)
        if c["fertig"]:
            _sig[uid] = await asyncio.to_thread(_stand, uid)
        print(f"wissen: wissenskarte doppelt geprueft | {c['auto']} zusammengefuehrt | {c['neu']} vorschlaege neu | "
              f"{c['offen']} offen | {c['weg']} weg | {c['vergleiche']} vergleiche | "
              + ("fertig" if c["fertig"] else "grenze"), flush=True)
        _live["d"] = None
        import live
        live.bg_done("Wissenskarte: Doppelte", True, time.time() - t0)
        return "wissensdoppelt"
    return None


# ---------------------------------------------------------------- reading for the owner
def _punkt(r, n):
    return {"id": r["id"], "name": r["name"], "n": n.get(r["id"], 0)}


def paare(uid, kid=None, most=PAARE_ZEIGEN):
    """The open suggestions of the profile (or of one point): {"paare": [{"a", "b", "art", "grund"}], "offen"}; a is
    the point with more places (the one to keep), b the one to merge into it. Read only."""
    with _Db(uid) as con:
        rows = con.execute(
            "SELECT p.a, p.b, p.art, p.grund FROM wk_paar p JOIN wk_ent x ON x.id = p.a JOIN wk_ent y ON y.id = p.b "
            "WHERE p.stand='offen' AND (? IS NULL OR p.a = ? OR p.b = ?) ORDER BY p.at, p.a, p.b", (kid, kid, kid)).fetchall()
        ids = {i for r in rows for i in (r["a"], r["b"])}
        ents = {r["id"]: r for r in con.execute("SELECT id, name FROM wk_ent WHERE id IN (SELECT value FROM json_each(?))",
                                                (json.dumps(sorted(ids)),))}
        n = {r[0]: r[1] for r in con.execute("SELECT ent, COUNT(*) FROM wk_ment WHERE ent IN (SELECT value FROM "
                                             "json_each(?)) GROUP BY ent", (json.dumps(sorted(ids)),))}
    rows = sorted(rows, key=lambda r: (_GRUND_RANG.get(r["grund"], 9), r["a"], r["b"]))
    out = []
    for r in rows[:most]:
        a, b = _punkt(ents[r["a"]], n), _punkt(ents[r["b"]], n)
        if (b["n"], -b["id"]) > (a["n"], -a["id"]):
            a, b = b, a
        out.append({"a": a, "b": b, "art": r["art"], "grund": r["grund"]})
    return {"paare": out, "offen": len(rows)}


def _paare_dice(x):
    s = f" {x} "
    return {s[i:i + 2] for i in range(len(s) - 1)}


def auswahl(uid, kid, q=""):
    """For „Zusammenführen mit …“ of one point: {"vielleicht": its open suggestions, "aehnlich": the AEHNLICH_MOST most
    similar points of the same kind (by aehnlich, then by shared pairs of letters), "treffer": at most TREFFER_MOST
    points of the kind whose name or other name holds q}. None when the point is not there. Read only."""
    with _Db(uid) as con:
        me = con.execute("SELECT id, art, name, alias FROM wk_ent WHERE id=?", (int(kid),)).fetchone()
        if not me:
            return None
        art = me["art"]
        rows = con.execute("SELECT id, name, alias FROM wk_ent WHERE art=? AND id<>? ORDER BY id", (art, me["id"])).fetchall()
        n = {r[0]: r[1] for r in con.execute("SELECT m.ent, COUNT(*) FROM wk_ment m JOIN wk_ent e ON e.id=m.ent "
                                             "WHERE e.art=? GROUP BY m.ent", (art,))}
    mine = _paare_dice(normalform(art, me["name"])[1])
    scored = []
    for r in rows:
        other = _paare_dice(normalform(art, r["name"])[1])
        scored.append((-2 * len(mine & other) / ((len(mine) + len(other)) or 1), r["id"], r))
    scored.sort(key=lambda x: x[:2])
    top = []
    for d, _, r in scored[:AEHNLICH_MOST * 6]:
        s, g = aehnlich(art, me["name"], r["name"])
        top.append(((0 if s else 1), d, r["id"], r, s, g))
    top.sort(key=lambda x: x[:3])
    aeh = [dict(_punkt(r, n), stufe=s or "", grund=g) for _, _, _, r, s, g in top[:AEHNLICH_MOST]]
    treffer = []
    qn = wk.ent_norm(q)[:wk.ENT_NAME_LEN]
    if qn:
        hits = [(0 if wk.ent_norm(r["name"]).startswith(qn) else 1, wk.ent_norm(r["name"]), r["id"], r) for r in rows
                if any(qn in wk.ent_norm(x) for x in _namen(r))]
        treffer = [_punkt(r, n) for *_, r in sorted(hits, key=lambda x: x[:3])[:TREFFER_MOST]]
    return {"art": art, "vielleicht": paare(uid, me["id"])["paare"], "aehnlich": aeh, "treffer": treffer}


def verschieden(uid, a, b, now=None):
    """The owner says two points are different: kept by their names, so the pair never comes back (neither as
    suggestion nor merged by itself). "ok", or why not: "gleich", "nicht da", "art"."""
    a, b = int(a), int(b)
    if a == b:
        return "gleich"
    a, b = min(a, b), max(a, b)
    with _Db(uid) as con:
        x = con.execute("SELECT * FROM wk_ent WHERE id=?", (a,)).fetchone()
        y = con.execute("SELECT * FROM wk_ent WHERE id=?", (b,)).fetchone()
        if not x or not y:
            return "nicht da"
        if x["art"] != y["art"]:
            return "art"
        g = con.execute("SELECT grund FROM wk_paar WHERE a=? AND b=?", (a, b)).fetchone()
        con.execute("INSERT OR REPLACE INTO wk_paar (a, b, art, grund, stand, na, nb, at) VALUES (?, ?, ?, ?, 'verschieden', "
                    "?, ?, ?)", (a, b, x["art"], g[0] if g else "schreibweise", wk.ent_norm(x["name"]), wk.ent_norm(y["name"]),
                                 int(now or time.time())))
        n = con.execute("SELECT COUNT(*) FROM wk_paar WHERE stand='verschieden'").fetchone()[0]
        if n > VERSCHIEDEN_MOST:
            con.execute("DELETE FROM wk_paar WHERE rowid IN (SELECT rowid FROM wk_paar WHERE stand='verschieden' "
                        "ORDER BY at, a, b LIMIT ?)", (n - VERSCHIEDEN_MOST,))
    ZAHLEN["verschieden"] += 1
    _live["d"] = None
    return "ok"


def for_live():
    """Live-Übersicht: open suggestions over all profiles, merged by itself and „Verschieden“ since the start (numbers
    only, never a name)."""
    if not wk.ents_on():
        return {"on": False}
    if _live["d"] is None or time.time() - _live["at"] >= LIVE_CACHE:
        offen = 0
        for uid in profiles.user_ids():
            if not wk.ents_allowed(uid) or not os.path.exists(documents.db_path(uid)):
                continue
            con = wk._lesen(uid)
            if con is None:
                continue
            try:
                if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='wk_paar'").fetchone():
                    offen += con.execute("SELECT COUNT(*) FROM wk_paar WHERE stand='offen'").fetchone()[0]
            finally:
                con.close()
        _live.update(at=time.time(), d={"offen": offen})
    return {"on": True, **_live["d"], **ZAHLEN}


# ---------------------------------------------------------------- endpoints
@router.get("/api/profile/wissenskarte/paare", dependencies=[Depends(assistant)])
async def show_pairs(request: Request, prof=Depends(own_profile)):
    """„Vielleicht doppelt“: the open suggestions of the own points (the map page and the apps)."""
    uid = prof["id"]
    wk._need_ents(uid)
    guard.limit(request, "wkarte", uid)
    got = await asyncio.to_thread(paare, uid)
    return dict(got, arten={k: list(wk.ENT_NAMEN[k]) for k in wk.ENT_ARTEN}, gruende=list(GRUENDE))


@router.get("/api/profile/wissenskarte/knoten/{kid}/aehnlich", dependencies=[Depends(assistant)])
async def similar(kid: int, request: Request, prof=Depends(own_profile)):
    """The suggestions of one point, its most similar points of the same kind and the search for „Zusammenführen mit“."""
    uid = prof["id"]
    wk._need_ents(uid)
    guard.limit(request, "wkarte", uid)
    q = request.query_params.get("q", "")
    if len(q) > wk.ENT_NAME_LEN:
        raise HTTPException(400, "q")
    got = await asyncio.to_thread(auswahl, uid, kid, q)
    if got is None:
        raise HTTPException(404, "no such point")
    return got


_SAY = {"gleich": (400, "the same"), "nicht da": (404, "no such point"), "art": (400, "only points of the same kind")}


@router.post("/api/profile/wissenskarte/paare/verschieden", dependencies=[Depends(assistant)])
async def different(request: Request, prof=Depends(browser_profile)):
    """The owner says two points are different (never the model); nothing is lost, so no code is needed."""
    uid = prof["id"]
    wk._need_ents(uid)
    guard.limit(request, "wbuch", uid)     # the changes of the knowledge book and map share one limit
    body = await json_body(request, 256)
    a, b = body.get("a"), body.get("b")
    if not all(isinstance(x, int) and not isinstance(x, bool) and 0 < x < 10 ** 12 for x in (a, b)):
        print("wissen: wissenskarte doppelt verschieden abgelehnt | ungueltig", flush=True)
        raise HTTPException(400, "a, b")
    got = await asyncio.to_thread(verschieden, uid, a, b)
    if got != "ok":
        print(f"wissen: wissenskarte doppelt verschieden abgelehnt | {got.replace(' ', '_')}", flush=True)
        raise HTTPException(*_SAY[got])
    print("wissen: wissenskarte doppelt verschieden | 1 paar", flush=True)
    return {"ok": True}
