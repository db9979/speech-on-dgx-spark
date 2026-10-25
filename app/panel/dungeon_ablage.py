"""KI-Dungeon-Master: Ablage der Runden (Punkt 14 of the review of 2026-10-24, Dominik „alles umsetzten“: „Eine Datei
je Runde mit Zwischenspeicher, eine kurze Antwort „nichts neu“ beim Nachfragen“).

Every round is a file of its own, the game's own values of all rounds (the day's pictures, the thumbs per world) stay
in the old file without the rounds:

    STATE/dungeon-runden/<rid>.json   one round (seats as hashes, heroes, actions, narration)
    STATE/dungeon-runden.json         {"bilder": …, "daumen_welt": …}

A cache in memory keeps every file's text by its change stamp (time in ns, size, inode): a read only opens a file
whose stamp changed and runs the fixes of old rounds (dungeon._fix) once for it; everything else is parsed from the
cache, a fresh copy for every caller (a caller may change it and write it back). A write puts only the rounds whose
text changed, removes the files of rounds that are gone and writes the shared values only when they changed. The old
file with every round inside is split once on the first read (lesen). The writers hold dungeon._lock as before.

stand(rid) is the round's change stamp: the table's poll answers „nichts neu“ while it and the few states outside the
file stay the same (dungeon.view_stand). runde(rid) and rids_von(uid) read one round or a profile's rounds without
the others (the map thread's may_see).

Journal lines „dungeon: ablage | …“ with fixed words and numbers only.
"""
import json
import os
import re
import threading

from common import STATE, read_json, write_json

DIR = os.path.join(STATE, "dungeon-runden")
FILE = os.path.join(STATE, "dungeon-runden.json")
GEMEINSAM = ("bilder", "daumen_welt")      # the shared values in FILE
RID = re.compile(r"r[0-9a-f]{10}")   # a round's id (dungeon._RID)
_NAME = re.compile(r"(r[0-9a-f]{10})\.json")
_cache = {}                # rid -> (stamp, text, owner, uids)
_shared = [None, ""]       # stamp and text of FILE
_mu = threading.RLock()


def _stamp(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def datei(rid):
    return os.path.join(DIR, rid + ".json")


def _index(rd):
    return rd.get("owner"), frozenset(p.get("uid") for p in (rd.get("plaetze") or {}).values() if isinstance(p, dict) and p.get("uid"))


def _split():
    """The old file with every round inside: each round into its own file once, the old file keeps the rest."""
    d = read_json(FILE, {})
    rs = d.get("runden") if isinstance(d, dict) else None
    if not isinstance(rs, dict):
        return
    for rid, rd in rs.items():
        if _NAME.fullmatch(rid + ".json") and isinstance(rd, dict) and not os.path.exists(datei(rid)):
            write_json(datei(rid), rd, mode=0o600, dir_mode=0o700)
    write_json(FILE, {k: d[k] for k in GEMEINSAM if isinstance(d.get(k), dict)}, mode=0o600, dir_mode=0o700)
    print(f"dungeon: ablage | aufgeteilt | {len(rs)} runden", flush=True)


def _load(rid, fix):
    """The round's text from the cache, read anew when its stamp changed; None when the file is gone or broken."""
    path = datei(rid)
    st = _stamp(path)
    c = _cache.get(rid)
    if c and c[0] == st:
        return c[1]
    if st is None:
        _cache.pop(rid, None)
        return None
    rd = read_json(path, {})
    if not rd:
        _cache.pop(rid, None)
        print("dungeon: ablage | runde | unlesbar", flush=True)
        return None
    if fix:
        fix(rd)
    text = json.dumps(rd)
    _cache[rid] = (st, text, *_index(rd))
    return text


def _rids():
    try:
        names = os.listdir(DIR)
    except OSError:
        return []
    return [m.group(1) for m in map(_NAME.fullmatch, names) if m]


def lesen(fix=None):
    """{"runden": {rid: round}, "bilder"?, "daumen_welt"?}: fresh copies, from the cache where nothing changed."""
    with _mu:
        if _stamp(FILE) != _shared[0]:
            _split()
            _shared[0], _shared[1] = _stamp(FILE), json.dumps(read_json(FILE, {}))
        out = {"runden": {}}
        for rid in _rids():
            text = _load(rid, fix)
            if text:
                out["runden"][rid] = json.loads(text)
        for rid in set(_cache) - set(out["runden"]):
            _cache.pop(rid, None)
        shared = json.loads(_shared[1]) if _shared[1] else {}
    for k in GEMEINSAM:
        if isinstance(shared.get(k), dict):
            out[k] = shared[k]
    return out


def schreiben(d, fix=None):
    """Writes the rounds whose text changed, removes the files of rounds no longer in d, the shared values when they
    changed. The caller holds dungeon._lock and read d with lesen. The cache keeps a written round as a read would
    give it (fix)."""
    rs = d.get("runden") or {}
    neu = weg = 0
    with _mu:
        for rid, rd in rs.items():
            if not _NAME.fullmatch(rid + ".json"):
                continue
            text = json.dumps(rd)
            c = _cache.get(rid)
            if c and c[1] == text and c[0] == _stamp(datei(rid)):
                continue
            write_json(datei(rid), rd, mode=0o600, dir_mode=0o700)
            if fix:
                rd2 = json.loads(text)
                fix(rd2)
                text = json.dumps(rd2)
            _cache[rid] = (_stamp(datei(rid)), text, *_index(rd))
            neu += 1
        for rid in set(_rids()) - set(rs):
            try:
                os.remove(datei(rid))
            except OSError:
                pass
            _cache.pop(rid, None)
            weg += 1
        shared = {k: d[k] for k in GEMEINSAM if isinstance(d.get(k), dict)}
        text = json.dumps(shared)
        if text != _shared[1] or _stamp(FILE) != _shared[0]:
            write_json(FILE, shared, mode=0o600, dir_mode=0o700)
            _shared[0], _shared[1] = _stamp(FILE), text
    if weg:
        print(f"dungeon: ablage | geschrieben | {neu} runden | {weg} weg", flush=True)


def runde(rid, fix=None):
    """One round (a fresh copy) without reading the others, or None."""
    if not _NAME.fullmatch(str(rid) + ".json"):
        return None
    with _mu:
        if _stamp(FILE) != _shared[0]:
            _split()
        text = _load(rid, fix)
    return json.loads(text) if text else None


def rids_von(uid, fix=None):
    """The rounds a profile hosts or sits at, from the cache (only changed files are read)."""
    with _mu:
        out = []
        for rid in _rids():
            if _load(rid, fix) and (_cache[rid][2] == uid or uid in _cache[rid][3]):
                out.append(rid)
    return out


def stand(rid):
    """The round's change stamp (for „nichts neu“), None without its file."""
    return _stamp(datei(rid)) if _NAME.fullmatch(str(rid) + ".json") else None


def vergessen():
    """Forget the cache (the self-tests between their rounds)."""
    with _mu:
        _cache.clear()
        _shared[0], _shared[1] = None, ""
