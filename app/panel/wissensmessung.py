"""Wissen messen (Wissenskarte Stufe 4, Dominik 2026-10-29 „Empfehlung umsetzen“): times and memory of the document
search, the Wissensbuch and the Wissenskarte, for the planned test with 5000 documents (Wissenskarte Stufe 2 waits for
it). Numbers only, never a title, a name, a sentence or a question: in the result, the journal and the Live view.

Two kinds of run, admin only (Zustand → Prüfen → Wissen messen, or sudo speech-spark wissen messen):
  synth   a throwaway profile of `anzahl` documents from a fixed seed (SEED): pieces with random float16 vectors,
          context lines, Wissensbuch pages and sentences, points from documents with their places, connections. It is
          built in a run folder under STATE/wissensmessung-tmp and removed after the run, whatever happened. The limits
          of the real code (wissensbuch.MAX_PAGES, wissenskarte.MAX_EDGES, wissenskarte.MAX_ENT and the ones per
          document) hold while building, and the run says how much more the documents would have brought (bedarf):
          so it shows whether a limit becomes the bottleneck. With ohne_grenzen (CLI only) it builds without them.
  profil  the documents of one real profile, read only: every connection of the measuring process gets
          PRAGMA query_only, a database of another schema version or without the tables of a part is not touched.

Both run in a measuring process of their own (this file, „kind“), never in the panel's event loop: low priority
(embed_worker.hinten: nice 10 and SCHED_IDLE, numpy with one thread), one run at a time on the Spark (a lock file,
also against the command line), at most every PAUSE_S seconds from the panel, at most MAX_S seconds. Speech goes
first: the panel waits for a quiet moment before it starts (vorrang.quiet), and the run stops as soon as somebody
speaks (vorrang.speaking, checked by both processes between every two queries); it is then „sprache“, not repeated.

Inside the measuring process the parts measure what the code can do, not what a profile's switches allow (the
release checks of wissensbuch and wissenskarte answer yes there); the process only reads and only gives numbers.

Messteile (the interface for other parts, e.g. the thread „Alles schnell finden über einen Index“ with "fund"):

    MESSTEILE = {"name": fn}
    fn(ordner, anzahl) -> {"key": number, ...}

fn works only inside `ordner`, the run's throwaway folder (made empty for this run, removed after it), never on a real
profile; `anzahl` is the number of documents (or mails, entries) it builds there. It returns numbers only (int, float,
bool; keys of a to z, 0 to 9 and _), e.g. p50_ms, p95_ms, max_ms, mb, ram_mb; anything else is dropped (_zahlen).
It may call ruhe() between steps, which stops the run while somebody speaks. The parts run one after the other in the
order of MESSTEILE in the same measuring process; the run keeps each part's dict under its name, writes one journal
line per part and shows the newest numbers in Live. The own parts documents, wissensbuch and wissenskarte share the
throwaway profile of the run (_synth builds it once per folder and number).

    GET  /api/admin/wissensmessung     running, the last KEEP runs (numbers), profiles to pick (admin only)
    POST /api/admin/wissensmessung     {"art": "synth", "anzahl": n} or {"art": "profil", "profil": id}: start one run
"""
import asyncio
import fcntl
import json
import os
import re
import secrets
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.dirname(HERE), HERE):          # the measuring process starts isolated (-I)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402

import core  # noqa: E402
import guard  # noqa: E402
import profiles  # noqa: E402
import vorrang  # noqa: E402
from common import STATE, write_json  # noqa: E402
from core import admin_code, auth  # noqa: E402

FILE = os.path.join(STATE, "wissensmessung.json")
TMP = os.path.join(STATE, "wissensmessung-tmp")
KEEP = 10                # runs kept
PROBEN = 20              # fixed sample queries per kind (from the profile's own titles and names)
SEED = 20261029          # the synthetic profile's fixed chance
ANZAHL = 5000            # documents of the synthetic profile (default)
ANZAHL_MIN, ANZAHL_MAX = 50, 20000
MAX_S = 1800             # seconds a run may take at most
PAUSE_S = 300            # seconds between two runs started from the panel
MAX_BODY = 512
JOB = "Wissen messen"    # the fixed name for vorrang and „Wer rechnet gerade“
UID = "messprofil"       # the throwaway profile's id inside its run folder
STATUS = ("fertig", "sprache", "zeit", "fehler", "leer", "alt")
KEY = re.compile(r"[a-z0-9_]{1,40}")
# the synthetic documents (assumptions, fixed; a real profile measured with „profil“ says what it really brings)
SYN_STUECKE = (3, 18)    # pieces per document
SYN_WORTE = (50, 120)    # words per piece
SYN_VOKABEL = 4000       # made-up words
SYN_SEITEN = 2           # Wissensbuch pages a document touches ...
SYN_SEITE_NEU = 0.3      # ... each a new one with this chance
SYN_SAETZE = (1, 3)      # sentences a document adds to a page
SYN_KNOTEN = (0, 12)     # places of points (people, companies, …) per document ...
SYN_KNOTEN_NEU = 0.35    # ... each a new point with this chance
SYN_KANTEN = (0, 8)      # connections per document

_KIND = [False]          # True only in the measuring process (the throwaway profile may only be built there)
_AUFBAU = {}             # the synthetic profile's numbers (measuring process): bedarf_*, aufbau_s
_proc = None             # the measuring process while it runs (rechenteile: „Wer rechnet gerade“)
_stand = {"laeuft": False, "art": "", "anzahl": 0, "seit": 0}
_letzter = [0.0]         # when the last run from the panel ended


class Abbruch(Exception):
    """The run stops (its word: sprache, zeit, laeuft …)."""


# ---------------------------------------------------------------- small helpers (also for other parts)
def ruhe():
    """Stops the run while somebody speaks (call it between steps; speech goes first)."""
    if vorrang.speaking():
        raise Abbruch("sprache")


def rss_mb():
    """The resident memory of this process in MB (Linux /proc, else the peak from getrusage)."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except (OSError, ValueError, IndexError):
        pass
    import resource
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)


def zeiten(name, fn, args_list):
    """Runs fn(*args) for every args, ruhe() before each, and gives {name_p50_ms, name_p95_ms, name_max_ms, name_n}."""
    ms = []
    for args in args_list:
        ruhe()
        t0 = time.perf_counter()
        fn(*args)
        ms.append((time.perf_counter() - t0) * 1000)
    if not ms:
        return {f"{name}_n": 0}
    s = sorted(ms)
    return {f"{name}_p50_ms": round(statistics.median(s), 2), f"{name}_p95_ms": round(s[max(0, -(-len(s) * 95 // 100) - 1)], 2),
            f"{name}_max_ms": round(s[-1], 2), f"{name}_n": len(s)}


def _verteilt(rows, n=PROBEN):
    """n rows spread evenly over a sorted list (always the same ones for the same data)."""
    if len(rows) <= n:
        return list(rows)
    return [rows[i * len(rows) // n] for i in range(n)]


def _zahlen(d, tiefe=0):
    """Only numbers under plain keys (one level of dicts below): what a part returns, before it is kept."""
    out = {}
    for k, v in (d.items() if isinstance(d, dict) else ()):
        if not isinstance(k, str) or not KEY.fullmatch(k):
            continue
        if isinstance(v, bool) or isinstance(v, int) and abs(v) < 10**15:
            out[k] = v
        elif isinstance(v, float) and v == v and abs(v) < 1e15:
            out[k] = round(v, 3)
        elif isinstance(v, dict) and tiefe < 2:
            out[k] = _zahlen(v, tiefe + 1)
    return out


# ---------------------------------------------------------------- the measuring process: read only, all released
def _alles_frei():
    """Measuring process only: the parts measure what the code can do, not a profile's switches."""
    import wissensbuch
    import wissenskarte
    yes = lambda uid: bool(uid)                                   # noqa: E731
    wissensbuch.allowed = yes
    wissenskarte.allowed = wissenskarte.ents_allowed = wissenskarte.suche_allowed = yes


def _nur_lesen():
    """Measuring process only („profil“): every connection to a profile's database refuses to write."""
    import documents
    orig = documents._open

    def lesend(uid):
        con = orig(uid)
        con.execute("PRAGMA query_only=1")
        return con
    documents._open = lesend


def _namen(schema):
    return set(re.findall(r"IF NOT EXISTS (\w+)", schema))


def _hat(con, schema):
    """True when the database holds every table, index and trigger of this schema."""
    have = {r[0] for r in con.execute("SELECT name FROM sqlite_master")}
    return _namen(schema) <= have


def _lesen(uid):
    """A read-only connection to the profile's wissen.db, or None."""
    import sqlite3
    import urllib.parse
    import documents
    path = documents.db_path(uid)
    if not os.path.exists(path):
        return None
    con = sqlite3.connect("file:" + urllib.parse.quote(path) + "?mode=ro", uri=True, timeout=15)
    con.row_factory = sqlite3.Row
    return con


def _teile_da(uid):
    """Which own parts the profile's database can be measured for without writing: {"documents", "wissensbuch",
    "wissenskarte"} ⊇ result; "alt" when its schema version is not this code's."""
    import documents
    import wissensbuch
    import wissenskarte
    con = _lesen(uid)
    if con is None:
        return set()
    try:
        if con.execute("PRAGMA user_version").fetchone()[0] != documents._schema_version():
            return "alt"
        da = {"documents"} if _hat(con, documents.SCHEMA) else set()
        cols = {r[1] for r in con.execute("PRAGMA table_info(wb_docs)")}
        if da and _hat(con, wissensbuch.SCHEMA) and "sig" in cols and \
                con.execute("SELECT 1 FROM sqlite_master WHERE name='wb_fts'").fetchone():
            da.add("wissensbuch")
            if _hat(con, wissenskarte.SCHEMA):
                da.add("wissenskarte")
        return da
    finally:
        con.close()


# ---------------------------------------------------------------- the own parts, on a profile id
def messe_documents(uid):
    """Pieces, vectors, the float16 matrix (MB, ms to build, memory before and after) and documents.search with and
    without the map over PROBEN titles of the profile's own documents (each with the vector of one of its pieces)."""
    import numpy as np
    import documents
    con = _lesen(uid)
    try:
        n_docs = con.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
        n_chunks = con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        n_vec = n_chunks - con.execute("SELECT COUNT(*) FROM chunks WHERE vec IS NULL").fetchone()[0]
        docs = _verteilt(con.execute("SELECT id, name, title FROM docs WHERE use=1 AND state='ready' ORDER BY id").fetchall())
        proben = []
        for d in docs:
            v = con.execute("SELECT vec FROM chunks WHERE doc=? AND vec IS NOT NULL ORDER BY n LIMIT 1", (d["id"],)).fetchone()
            q = documents._title(d)
            proben.append((q, np.frombuffer(v[0], dtype=np.float16).astype(np.float32) if v else None))
    finally:
        con.close()
    ruhe()
    vorher = rss_mb()
    t0 = time.perf_counter()
    _, mat = documents._vectors(uid)
    out = {"dokumente": n_docs, "stuecke": n_chunks, "vektoren": n_vec,
           "matrix_ms": round((time.perf_counter() - t0) * 1000, 1),
           "matrix_mb": round(mat.nbytes / 1024**2, 2) if mat is not None else 0,
           "ram_vorher_mb": vorher, "ram_matrix_mb": rss_mb()}
    out.update(zeiten("suche", lambda q, v: documents.search(uid, q, k=5, qvec=v), proben))
    out.update(zeiten("suche_karte", lambda q, v: documents.search(uid, q, k=5, qvec=v, karte=True), proben))
    out["ram_mb"] = rss_mb()
    return out


def messe_wissensbuch(uid):
    """Pages, sentences, pages per worked-in document and wissensbuch.liste over PROBEN page titles."""
    import wissensbuch
    con = _lesen(uid)
    try:
        pages = con.execute("SELECT COUNT(*) FROM wb_pages").fetchone()[0]
        sents = con.execute("SELECT COUNT(*) FROM wb_sent").fetchone()[0]
        done = con.execute("SELECT COUNT(*) FROM wb_docs WHERE state='ok'").fetchone()[0]
        titles = [r[0] for r in _verteilt(con.execute("SELECT title FROM wb_pages ORDER BY id").fetchall())]
    finally:
        con.close()
    out = {"seiten": pages, "saetze": sents, "dokumente_eingearbeitet": done,
           "seiten_je_dok": round(pages / done, 3) if done else 0, "seiten_grenze": wissensbuch.MAX_PAGES}
    out.update(zeiten("liste", lambda q: wissensbuch.liste(uid, q, wissensbuch.LISTE_MOST), [(t,) for t in titles]))
    out["ram_mb"] = rss_mb()
    return out


def messe_wissenskarte(uid):
    """Points (pages and points from documents), connections, places, connections per document and the times of
    view (the best connected and around a point), rund_um (2 steps), weg and liste over PROBEN fixed points."""
    import wissenskarte
    con = _lesen(uid)
    try:
        q1 = lambda sql: con.execute(sql).fetchone()[0]                                  # noqa: E731
        pages, ents, edges = q1("SELECT COUNT(*) FROM wb_pages"), q1("SELECT COUNT(*) FROM wk_ent"), q1("SELECT COUNT(*) FROM wk_edges")
        ments = q1("SELECT COUNT(*) FROM wk_ment")
        kdocs, entdocs = q1("SELECT COUNT(*) FROM wk_docs"), q1("SELECT COUNT(*) FROM wk_entdocs")
        per = [r[0] for r in con.execute("SELECT COUNT(*) FROM wk_edges GROUP BY doc")]
        knoten = [r[0] for r in con.execute(
            "SELECT x FROM (SELECT a AS x FROM wk_edges UNION SELECT b FROM wk_edges) ORDER BY x")]
        namen = [r[0] for r in _verteilt(con.execute("SELECT name FROM wk_ent ORDER BY id").fetchall())]
    finally:
        con.close()
    probe = _verteilt(knoten)
    paare = [(probe[i], probe[(i + len(probe) // 2) % len(probe)]) for i in range(len(probe))] if probe else []
    out = {"seiten": pages, "punkte": ents, "knoten": pages + ents, "kanten": edges, "stellen": ments,
           "dokumente_mit_kanten": len(per), "dokumente_verbunden": kdocs, "dokumente_mit_punkten": entdocs,
           "kanten_je_dok": round(edges / kdocs, 3) if kdocs else 0, "kanten_je_dok_max": max(per) if per else 0,
           "punkte_je_dok": round(ents / entdocs, 3) if entdocs else 0,
           "kanten_grenze": wissenskarte.MAX_EDGES, "punkte_grenze": wissenskarte.MAX_ENT}
    out.update(zeiten("view", lambda: wissenskarte.view(uid), [()] * min(5, PROBEN)))
    out.update(zeiten("view_um", lambda k: wissenskarte.view(uid, um=k), [(k,) for k in probe]))
    out.update(zeiten("rund_um", lambda k: wissenskarte.rund_um(uid, k, 2), [(k,) for k in probe]))
    out.update(zeiten("weg", lambda a, b: wissenskarte.weg(uid, a, b), paare))
    out.update(zeiten("liste", lambda n: wissenskarte.liste(uid, n), [(n,) for n in namen]))
    out["ram_mb"] = rss_mb()
    return out


EIGENE = {"documents": messe_documents, "wissensbuch": messe_wissensbuch, "wissenskarte": messe_wissenskarte}


# ---------------------------------------------------------------- the throwaway profile (measuring process only)
def _im_ordner(ordner):
    """Points the profiles at ordner/users; only in the measuring process and only in a run folder (lauf-… under a
    folder named like TMP), never a profile folder."""
    real = os.path.realpath(ordner)
    if not _KIND[0] or not os.path.basename(real).startswith("lauf-") or \
            os.path.basename(os.path.dirname(real)) != os.path.basename(TMP):
        raise RuntimeError("only in the measuring process, inside its run folder")
    profiles.USERS_DIR = os.path.join(real, "users")


def _wort(rnd):
    silben = ("ka", "lo", "ver", "min", "do", "ra", "te", "sul", "bor", "an", "ni", "quel", "fa", "mer", "ost", "il",
              "pra", "dun", "es", "go", "rin", "tal", "ve", "so", "kur", "len", "ba", "hi", "wor", "zen")
    return "".join(rnd.choice(silben) for _ in range(rnd.randint(2, 4)))


def _synth(ordner, anzahl, grenzen=True):
    """The throwaway profile in ordner with anzahl documents from SEED (built once per folder and number): its id."""
    import random
    import numpy as np
    import docembed
    import documents
    import wissensbuch
    import wissenskarte
    _im_ordner(ordner)
    mark = f"{anzahl}:{SEED}:{int(grenzen)}"
    if _AUFBAU.get("mark") == mark and os.path.exists(documents.db_path(UID)):
        return UID
    t0 = time.time()
    rnd = random.Random(SEED)                        # data for a measurement, never for a secret
    npr = np.random.default_rng(SEED)
    vok = [_wort(rnd) for _ in range(SYN_VOKABEL)]
    hexid = lambda: "%012x" % rnd.getrandbits(48)   # noqa: E731
    seiten, punkte, bedarf = [], [], {"seiten": 0, "punkte": 0, "kanten": 0}
    kanten = 0
    now = int(time.time())
    for start in range(0, anzahl, 250):
        ruhe()
        batch = []
        with documents._Db(UID) as con:
            for i in range(start, min(anzahl, start + 250)):
                doc = hexid()
                title = " ".join(w.capitalize() for w in rnd.sample(vok, 3))
                con.execute("INSERT INTO docs (id, name, size, created, kind, state, pages, use, title, art) VALUES "
                            "(?,?,?,?,'text','ready',?,1,?,?)", (doc, f"dok-{i:05d}.pdf", 50000, now - i, 3, title,
                                                                  rnd.choice(documents.ARTS)))
                n = rnd.randint(*SYN_STUECKE)
                for c in range(n):
                    words = [rnd.choice(vok) for _ in range(rnd.randint(*SYN_WORTE))]
                    documents._put_chunk(con, doc, c, 1 + c // 4, " ".join(words) + ".", part="")
                documents.set_heads(con, doc)
                ids = [r[0] for r in con.execute("SELECT id FROM chunks WHERE doc=? ORDER BY n", (doc,))]
                vec = npr.standard_normal((len(ids), docembed.DIM)).astype(np.float32)
                vec /= np.linalg.norm(vec, axis=1, keepdims=True)
                con.executemany("UPDATE chunks SET vec=? WHERE id=?",
                                [(v.astype(np.float16).tobytes(), cid) for v, cid in zip(vec, ids)])
                batch.append((doc, n))
        with wissenskarte._Db(UID) as con:
            for doc, n in batch:
                # Wissensbuch: a few pages per document, sometimes a new one (MAX_PAGES holds)
                mine = []
                for _ in range(min(SYN_SEITEN, wissensbuch.PAGES_PER_DOC)):
                    if not seiten or rnd.random() < SYN_SEITE_NEU:
                        bedarf["seiten"] += 1
                        if not grenzen or len(seiten) < wissensbuch.MAX_PAGES:
                            pid = hexid()
                            con.execute("INSERT INTO wb_pages (id, title, art, made, changed) VALUES (?,?,?,?,?)",
                                        (pid, " ".join(w.capitalize() for w in rnd.sample(vok, 2)),
                                         rnd.choice(wissensbuch.ARTS), now, now))
                            seiten.append(pid)
                            mine.append(pid)
                            continue
                    if seiten:
                        mine.append(rnd.choice(seiten))
                for pid in set(mine):
                    have = con.execute("SELECT COUNT(*) FROM wb_sent WHERE page=?", (pid,)).fetchone()[0]
                    for _ in range(min(rnd.randint(*SYN_SAETZE), max(0, wissensbuch.MAX_SENT - have) if grenzen else 99)):
                        s = " ".join(rnd.choice(vok) for _ in range(9)) + "."
                        con.execute("INSERT INTO wb_sent (page, text, norm, doc, part, dpage, made) VALUES (?,?,?,?,?,?,?)",
                                    (pid, s, wissensbuch.norm(s), doc, rnd.randrange(n), 1, now))
                con.execute("INSERT OR REPLACE INTO wb_docs (doc, state, at, sig) VALUES (?, 'ok', ?, '')", (doc, now))
                # points from documents: places in its pieces, new ones until MAX_ENT
                eigene = []
                for _ in range(min(rnd.randint(*SYN_KNOTEN), wissenskarte.ENT_PER_DOC)):
                    if not punkte or rnd.random() < SYN_KNOTEN_NEU:
                        bedarf["punkte"] += 1
                        if not grenzen or len(punkte) < wissenskarte.MAX_ENT:
                            art = rnd.choice(wissenskarte.ENT_ARTEN)
                            name = " ".join(w.capitalize() for w in rnd.sample(vok, 2))
                            cur = con.execute("INSERT OR IGNORE INTO wk_ent (art, name, norm) VALUES (?,?,?)",
                                              (art, name, wissenskarte.ent_norm(name)))
                            if cur.rowcount:
                                punkte.append(cur.lastrowid)
                                eigene.append(cur.lastrowid)
                            continue
                    if punkte:
                        eigene.append(punkte[min(len(punkte) - 1, int(rnd.paretovariate(1.2)) - 1)]
                                      if rnd.random() < 0.5 else rnd.choice(punkte))
                for ent in set(eigene):
                    con.execute("INSERT OR IGNORE INTO wk_ment (ent, doc, chunk) VALUES (?,?,?)", (ent, doc, rnd.randrange(n)))
                con.execute("INSERT OR REPLACE INTO wk_entdocs (doc, state, at, sig) VALUES (?, 'ok', ?, '')", (doc, now))
                # connections between its pages and points (EDGES_PER_DOC per document, MAX_EDGES per profile)
                ends = list(set(mine)) + [f"k{e}" for e in set(eigene)]
                want = min(rnd.randint(*SYN_KANTEN), wissenskarte.EDGES_PER_DOC) if len(ends) > 1 else 0
                for _ in range(want):
                    bedarf["kanten"] += 1
                    if grenzen and kanten >= wissenskarte.MAX_EDGES:
                        continue
                    a, b = rnd.sample(ends, 2)
                    con.execute("INSERT INTO wk_edges (a, b, art, detail, doc, part, dpage, made) VALUES (?,?,?,'',?,?,1,?)",
                                (a, b, rnd.choice(list(wissenskarte.ARTEN)), doc, rnd.randrange(n), now))
                    kanten += 1
                con.execute("INSERT OR REPLACE INTO wk_docs (doc, state, at, sig) VALUES (?, 'ok', ?, '')", (doc, now))
    _AUFBAU.clear()
    _AUFBAU.update(mark=mark, aufbau_s=round(time.time() - t0, 1), grenzen=grenzen, **{f"bedarf_{k}": v for k, v in bedarf.items()})
    return UID


def teil_documents(ordner, anzahl):
    return messe_documents(_synth(ordner, anzahl, _GRENZEN[0]))


def teil_wissensbuch(ordner, anzahl):
    return messe_wissensbuch(_synth(ordner, anzahl, _GRENZEN[0]))


def teil_wissenskarte(ordner, anzahl):
    return messe_wissenskarte(_synth(ordner, anzahl, _GRENZEN[0]))


_GRENZEN = [True]        # measuring process: build the throwaway profile with the limits of the real code
# the parts of a synthetic run, in this order (other parts add their own entry here; interface: see the top)
MESSTEILE = {
    "documents": teil_documents,
    "wissensbuch": teil_wissensbuch,
    "wissenskarte": teil_wissenskarte,
}


def _kind(argv):
    """The measuring process: kind synth <anzahl> <ordner> [ohne] | kind profil <uid>. Writes one JSON line."""
    import embed_worker
    _KIND[0] = True
    out, sys.stdout = sys.stdout, sys.stderr          # lines of the parts go to the journal, the result alone here
    embed_worker.hinten(True)
    res = {"ram_start_mb": rss_mb(), "teile": {}}
    try:
        _alles_frei()
        if argv[0] == "synth":
            anzahl, ordner = int(argv[1]), argv[2]
            _GRENZEN[0] = "ohne" not in argv[3:]
            for name, fn in MESSTEILE.items():
                ruhe()
                res["teile"][name] = fn(ordner, anzahl)
            res["aufbau"] = {k: v for k, v in _AUFBAU.items() if k != "mark"}
        else:
            uid = argv[1]
            da = _teile_da(uid)
            if da == "alt" or not da:
                raise Abbruch("alt" if da == "alt" else "leer")
            _nur_lesen()
            for name, fn in EIGENE.items():
                if name in da:
                    ruhe()
                    res["teile"][name] = fn(uid)
        res["status"] = "fertig"
    except Abbruch as e:
        res["status"] = str(e)
    except Exception as e:   # noqa: BLE001
        res.update(status="fehler", fehler=type(e).__name__)
    res["ram_ende_mb"] = rss_mb()
    out.write(json.dumps(res) + "\n")
    out.flush()


# ---------------------------------------------------------------- one run (panel thread or command line)
def _engpaesse(res, art, anzahl):
    """Per limit: the limit, what the documents bring (synth: what the build wanted; profil: the profile's rate per
    document times max(ANZAHL, its documents), an upper estimate) and whether it is full (voll)."""
    import wissensbuch
    import wissenskarte
    t = res.get("teile") or {}
    wb, wk = t.get("wissensbuch") or {}, t.get("wissenskarte") or {}
    auf = res.get("aufbau") or {}
    n = max(ANZAHL, int((t.get("documents") or {}).get("dokumente", 0)))
    rows = {"seiten": (wissensbuch.MAX_PAGES, wb.get("seiten", 0), auf.get("bedarf_seiten"), wb.get("seiten_je_dok", 0)),
            "kanten": (wissenskarte.MAX_EDGES, wk.get("kanten", 0), auf.get("bedarf_kanten"), wk.get("kanten_je_dok", 0)),
            "punkte": (wissenskarte.MAX_ENT, wk.get("punkte", 0), auf.get("bedarf_punkte"), wk.get("punkte_je_dok", 0))}
    out = {}
    for k, (grenze, jetzt, bedarf, rate) in rows.items():
        bedarf = int(bedarf) if art == "synth" and bedarf is not None else int(round(rate * n))
        out[k] = {"grenze": grenze, "jetzt": jetzt, "bedarf": bedarf, "voll": bedarf > grenze}
    return out


def _zeile(name, d):
    """One journal line per part: fixed words and numbers only."""
    ms = [f"{k[:-7]} p95 {d[k]:.0f} ms" for k in sorted(d) if k.endswith("_p95_ms")]
    n = [f"{k} {d[k]}" for k in ("dokumente", "stuecke", "seiten", "punkte", "kanten") if k in d]
    mb = [f"matrix {d['matrix_mb']} mb"] if "matrix_mb" in d else []
    return " | ".join(n + mb + ms + [f"ram {d.get('ram_mb', 0)} mb"])


def lauf(art, anzahl=ANZAHL, uid="", grenzen=True, sprache=None, warten=time.sleep, kind_env=None, now=None):
    """One run (blocking, in a worker thread or on the command line): the result, also kept in FILE. Raises
    Abbruch("laeuft") while another run holds the lock. sprache: the check whether somebody speaks (vorrang.speaking)."""
    global _proc
    sprache = sprache or vorrang.speaking
    os.makedirs(TMP, mode=0o700, exist_ok=True)
    lk = os.open(os.path.join(TMP, ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(lk)
        print("wissen: messung abgelehnt | laeuft", flush=True)
        raise Abbruch("laeuft")
    t0 = time.time() if now is None else now
    res = {"id": secrets.token_hex(6), "zeit": int(t0), "art": art, "anzahl": int(anzahl) if art == "synth" else 0,
           "profil": uid if art == "profil" else "", "grenzen": bool(grenzen)}
    _stand.update(laeuft=True, art=art, anzahl=res["anzahl"], seit=int(t0))
    for alt in os.listdir(TMP):                      # a run that died with its folder
        if alt.startswith("lauf-"):
            shutil.rmtree(os.path.join(TMP, alt), ignore_errors=True)
    ordner = tempfile.mkdtemp(prefix="lauf-", dir=TMP)
    print("wissen: messung gestartet | " + (f"synth {res['anzahl']}" if art == "synth" else "profil"), flush=True)
    try:
        if sprache():
            raise Abbruch("sprache")
        cmd = [sys.executable, "-I", os.path.abspath(__file__), "kind"] + (
            ["synth", str(res["anzahl"]), ordner] + ([] if grenzen else ["ohne"]) if art == "synth" else ["profil", uid])
        env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1", **(kind_env or {}))
        _proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, env=env)
        grund = None
        while _proc.poll() is None:
            if sprache():
                grund = "sprache"
            elif time.time() - t0 > MAX_S:
                grund = "zeit"
            if grund:
                _proc.kill()
                _proc.wait()
                raise Abbruch(grund)
            warten(0.5)
        raw = (_proc.stdout.read() or b"").decode("utf-8", "replace").strip().splitlines()
        got = json.loads(raw[-1]) if raw else {}
        status = got.get("status") if got.get("status") in STATUS else "fehler"
        res.update(_zahlen({k: got.get(k) for k in ("ram_start_mb", "ram_ende_mb", "teile", "aufbau")}), status=status)
        if status == "fehler":
            res["fehler"] = got.get("fehler") if isinstance(got.get("fehler"), str) and KEY.fullmatch(got["fehler"].lower()) else ""
    except Abbruch as e:
        res["status"] = str(e)
    except (OSError, ValueError) as e:
        res.update(status="fehler", fehler=type(e).__name__)
    finally:
        if _proc is not None and _proc.poll() is None:
            _proc.kill()
            _proc.wait()
        if _proc is not None and _proc.stdout:
            _proc.stdout.close()
        _proc = None
        shutil.rmtree(ordner, ignore_errors=True)
        _stand.update(laeuft=False)
        fcntl.flock(lk, fcntl.LOCK_UN)
        os.close(lk)
    res["dauer_s"] = round(time.time() - t0, 1)
    if res["status"] == "fertig":
        res["engpaesse"] = _engpaesse(res, art, res["anzahl"])
    try:
        from core import app_version
        res["version"] = app_version()
    except Exception:   # noqa: BLE001
        res["version"] = ""
    write_json(FILE, ([res] + laeufe())[:KEEP])
    for name, d in (res.get("teile") or {}).items():
        print(f"wissen: messung teil {name} | {_zeile(name, d)}", flush=True)
    if res["status"] == "fertig":
        voll = [k for k, v in res["engpaesse"].items() if v["voll"]]
        print(f"wissen: messung fertig | {res['dauer_s']:.0f} s | engpass " + (" ".join(voll) or "keiner"), flush=True)
    else:
        print(f"wissen: messung abgebrochen | {res['status']}" + (f" {res['fehler']}" if res.get("fehler") else ""),
              flush=True)
    return res


def laeufe():
    """The kept runs, newest first (checked again: known keys, numbers, fixed words)."""
    try:
        with open(FILE, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return []
    out = []
    for r in d if isinstance(d, list) else []:
        if not isinstance(r, dict) or not re.fullmatch(r"[0-9a-f]{12}", str(r.get("id"))) or r.get("status") not in STATUS:
            continue
        x = _zahlen({k: r.get(k) for k in ("zeit", "anzahl", "grenzen", "dauer_s", "ram_start_mb", "ram_ende_mb",
                                           "teile", "aufbau", "engpaesse")})
        x.update(id=r["id"], status=r["status"], art=r.get("art") if r.get("art") in ("synth", "profil") else "",
                 profil=r.get("profil") if re.fullmatch(r"[\w-]{1,64}", str(r.get("profil"))) else "",
                 version=r.get("version") if re.fullmatch(r"V[\d.]{1,20}", str(r.get("version"))) else "",
                 fehler=r["fehler"] if isinstance(r.get("fehler"), str) and KEY.fullmatch(r["fehler"].lower()) else "")
        out.append(x)
    return out[:KEEP]


# ---------------------------------------------------------------- Live (numbers only)
def for_live():
    """Zustand → Live, box „Wissen messen“: running (kind, documents), or the newest run's numbers; off without either."""
    r = laeufe()
    if not _stand["laeuft"] and not r:
        return {"on": False}
    out = {"on": True, "laeuft": _stand["laeuft"], "art": _stand["art"], "anzahl": _stand["anzahl"]}
    if r:
        t = r[0].get("teile") or {}
        d, k = t.get("documents") or {}, t.get("wissenskarte") or {}
        out["letzte"] = {"status": r[0]["status"], "dokumente": d.get("dokumente", 0), "suche_p95_ms": d.get("suche_p95_ms", 0),
                         "karte_p95_ms": d.get("suche_karte_p95_ms", 0), "matrix_mb": d.get("matrix_mb", 0),
                         "weg_p95_ms": k.get("weg_p95_ms", 0), "teile": len(t),
                         "voll": sum(1 for v in (r[0].get("engpaesse") or {}).values() if v.get("voll"))}
    return out


def live_sub(v):
    """The Live box's line (fixed words and numbers)."""
    if v.get("laeuft"):
        return "misst gerade" + (f" · {v['anzahl']} Dokumente synthetisch" if v.get("art") == "synth" else " · ein Profil")
    x = v.get("letzte") or {}
    if x.get("status") != "fertig":
        return f"letzte Messung abgebrochen ({x.get('status', '')})"
    return (f"{x['dokumente']} Dokumente · Suche p95 {x['suche_p95_ms']:.0f} ms · mit Karte p95 {x['karte_p95_ms']:.0f} ms"
            f" · Weg p95 {x['weg_p95_ms']:.0f} ms · Matrix {x['matrix_mb']} MB · {x['teile']} Teile"
            + (f" · {x['voll']} Grenzen voll" if x.get("voll") else ""))


# ---------------------------------------------------------------- the page (admins only)
def _profile():
    """The profiles with documents, for the admin's pick (id and name, as Personen und Geräte shows them)."""
    import documents
    return [{"id": p["id"], "name": p["name"]} for p in profiles.names() if os.path.exists(documents.db_path(p["id"]))]


def daten(now=None):
    now = time.time() if now is None else now
    return {"laeuft": _stand["laeuft"], "art": _stand["art"], "anzahl": _stand["anzahl"], "seit": _stand["seit"],
            "warten": 0 if _stand["laeuft"] else max(0, int(PAUSE_S - (now - _letzter[0]))),
            "laeufe": laeufe(), "profile": _profile(), "standard": ANZAHL, "min": ANZAHL_MIN, "max": ANZAHL_MAX}


router = APIRouter()


@router.get("/api/admin/wissensmessung", dependencies=[Depends(auth)])
async def admin_state(request: Request):
    """Zustand → Prüfen → Wissen messen: running, the last runs (numbers), the profiles with documents."""
    guard.limit(request, "pruef", admin=True)
    return await asyncio.to_thread(daten)


@router.post("/api/admin/wissensmessung", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_start(request: Request):
    """„Messen“: one run in the background after a quiet moment; the code („Bestätigen“): it reads a profile."""
    guard.limit(request, "wmessen", admin=True)
    body = await core.json_body(request, MAX_BODY)
    art = body.get("art")
    anzahl, uid = body.get("anzahl", ANZAHL), body.get("profil", "")
    if art not in ("synth", "profil") or art == "synth" and (
            not isinstance(anzahl, int) or isinstance(anzahl, bool) or not ANZAHL_MIN <= anzahl <= ANZAHL_MAX):
        print("wissen: messung abgelehnt | ungueltig", flush=True)
        raise HTTPException(400, f"art: synth with anzahl {ANZAHL_MIN} to {ANZAHL_MAX}, or profil with a profile")
    if art == "profil" and (not isinstance(uid, str) or uid not in {p["id"] for p in await asyncio.to_thread(_profile)}):
        print("wissen: messung abgelehnt | kein profil", flush=True)
        raise HTTPException(404, "no profile with documents")
    if _stand["laeuft"]:
        print("wissen: messung abgelehnt | laeuft", flush=True)
        raise HTTPException(409, "a measurement is running")
    left = PAUSE_S - (time.time() - _letzter[0])
    if left > 0:
        print("wissen: messung abgelehnt | zu oft", flush=True)
        raise HTTPException(429, f"again in {int(left // 60) + 1} min", headers={"Retry-After": str(int(left))})
    _stand.update(laeuft=True, art=art, anzahl=anzahl if art == "synth" else 0, seit=int(time.time()))
    name = profiles.log_name(next((p for p in profiles.names() if p["id"] == uid), None)) if art == "profil" else ""

    async def hinten():
        try:
            await vorrang.quiet(JOB)
            await asyncio.to_thread(lauf, art, anzahl if art == "synth" else 0, uid if art == "profil" else "")
        except Abbruch:
            pass
        except Exception as e:   # noqa: BLE001
            print(f"wissen: messung fehler | {type(e).__name__}", flush=True)
        finally:
            _stand.update(laeuft=False)
            _letzter[0] = time.time()
    _letzter[0] = time.time()
    asyncio.get_running_loop().create_task(hinten())
    print("wissen: messung angefragt | " + (f"synth {anzahl}" if art == "synth" else f"profil {name}".strip()), flush=True)
    return await asyncio.to_thread(daten)


# ---------------------------------------------------------------- command line (sudo speech-spark wissen messen …)
def _cli(argv):
    """messen [synth [anzahl] [--ohne-grenzen] | profil <name>] [--json]: one run, prints numbers."""
    want_json = "--json" in argv
    args = [a for a in argv if not a.startswith("--")]
    art = args[0] if args else "synth"
    if art == "synth":
        anzahl = int(args[1]) if len(args) > 1 and args[1].isdigit() else ANZAHL
        if not ANZAHL_MIN <= anzahl <= ANZAHL_MAX:
            print(f"wissen: messung abgelehnt | anzahl {ANZAHL_MIN} bis {ANZAHL_MAX}")
            return 2
        uid = ""
    elif art == "profil" and len(args) > 1:
        hits = [p["id"] for p in profiles.names() if p["name"].lower() == args[1].lower()]
        if len(hits) != 1:
            print("wissen: messung abgelehnt | kein profil")
            return 2
        uid, anzahl = hits[0], 0
    else:
        print("wissen: messung aufruf | speech-spark wissen messen [synth [anzahl] [--ohne-grenzen] | profil <name>] [--json]")
        return 2
    out = sys.stdout
    if want_json:                                    # the journal lines to stderr, the result alone on stdout
        sys.stdout = sys.stderr
    try:
        res = lauf(art, anzahl, uid, grenzen="--ohne-grenzen" not in argv)
    except Abbruch as e:
        print(f"wissen: messung abgelehnt | {e}")
        return 1
    finally:
        sys.stdout = out
    if want_json:
        sys.stdout.write(json.dumps(res, indent=1) + "\n")       # the result alone, for scripts
    else:
        for k, v in (res.get("aufbau") or {}).items():
            print(f"wissen: messung aufbau | {k} {v}")
        for name, d in (res.get("teile") or {}).items():
            for k in sorted(d):
                print(f"wissen: messung {name} | {k} {d[k]}")
        for k, v in (res.get("engpaesse") or {}).items():
            print(f"wissen: messung grenze {k} | {v['jetzt']} jetzt | {v['bedarf']} bedarf | grenze {v['grenze']}"
                  + (" | voll" if v["voll"] else ""))
        print(f"wissen: messung status | {res['status']} | {res['dauer_s']} s")
    return 0 if res["status"] == "fertig" else 1


if __name__ == "__main__":
    if sys.argv[1:2] == ["kind"]:
        _kind(sys.argv[2:])
    elif sys.argv[1:2] == ["cli"]:
        sys.exit(_cli(sys.argv[2:]))
    else:
        sys.exit("usage: wissensmessung.py cli messen …")
