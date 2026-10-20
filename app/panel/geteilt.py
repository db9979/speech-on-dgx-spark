"""Teilen zwischen Profilen (plan teilen-profile/plan.md, Dominik 2026-10-20 „ok“): one way to share for every kind.

A thin layer over the ways that were already there; what is shared stays with its owner, in the owner's own file,
and nothing moves (1a). Each kind is an adapter with the same four questions: what the owner shares with whom
(people), what the others share with this profile (theirs), whether a profile may see it (level) and how a share
is set or taken back (put). The kinds of Stufe 1:

    doc   Dokumente: one document to single profiles. Kept here, users/<owner>/geteilt.json {"doc": {doc id:
          {profile id: {"level": "see", "t": when}}}}; "Für alle" (documents.shared, function docshared) stays as it
          was and shows in the dialog as „Alle Profile“. Found in the other's search while shared (wissen._offer).
    cal   Kalender teilen (calendars.set_share, function calshare): "see" or "add", set in its own dialog (one of
          the calendars of an address, C2), listed and taken back here.
    list  Listen teilen (tasks.set_share, function listshare): "see" or "add" (Mitschreiben), set in its own dialog,
          listed and taken back here.

The levels are the same everywhere: "see" and "add" (add is called after its kind: Mitschreiben, Sehen + eintragen,
Bearbeiten). Deleting, renaming and sharing on stay with the owner. Taking back works at once: every read asks the
owner's file anew (level), nothing is copied to the other profile.

Rules (fixed, never the model): only with the function Teilen (chat.share) released for both profiles and the
kind's own function for both; never with guests (no profile) or a voice the speaker did not recognize (they get no
tools and no personal data, chat_turn); the other profile only by its id from the list of profiles. What another
profile shares is outside text for the assistant (wissen.search, chat.READS_OUTSIDE) and never goes into the
memory or the Wissensbuch. A new share sends the other one note (push.send, tag "share"), at most one every
NOTE_GAP seconds per profile, more are counted into the next one; the note can be switched off (pref share_note).
Live and the journal get kinds and numbers only, never a title or a name.

    GET  /api/profile/geteilt                    Ich → Geteilt: {"theirs": [...], "mine": [...], "new": n}
    GET  /api/profile/teilen/{kind}/{id}         the dialog: the item, the profiles with their level, „Alle Profile“
    PUT  /api/profile/teilen/{kind}/{id}         {"to": profile id, "level": "see" | "add" | ""} or {"all": bool}
"""
import asyncio
import json
import os
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import profiles
from core import assistant, browser_profile, json_body, secret_profile

KINDS = ("doc", "cal", "list")
LEVELS = ("see", "add")
FEATURE = {"doc": "documents", "cal": "calshare", "list": "listshare"}   # the kind's own function, for both profiles
KIND_LEVELS = {"doc": ("see",), "cal": ("see", "add"), "list": ("see", "add")}   # what each kind can give
NOTE_GAP = 600           # one note per profile at most every 10 minutes (plan 6a)
MAX_PER_ITEM = 50        # profiles one item is shared with
MAX_ITEMS = 500          # items of one kind one profile shares (kept in its geteilt.json)
_ID = re.compile(r"u_[0-9a-f]{12}")
_DOC = re.compile(r"[0-9a-f]{12}")

_lock = threading.Lock()
_cache = {}              # uid -> (mtime, data): the files are read on every search of every other profile
_note = {}               # uid -> {"t": last note, "n": shares since, "task": waiting send}
_today = {"day": "", "set": 0, "back": 0}


def _file(uid):
    return profiles._path(uid, "geteilt.json")


def _load(uid):
    p = _file(uid)
    try:
        m = os.stat(p).st_mtime_ns
    except OSError:
        return {"doc": {}, "seen": 0}
    hit = _cache.get(uid)
    if hit and hit[0] == m:
        return hit[1]
    try:
        with open(p) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d = d if isinstance(d, dict) else {}
    docs = d.get("doc") if isinstance(d.get("doc"), dict) else {}
    out = {"doc": {k: {u: {"level": v["level"], "t": int(v.get("t") or 0)} for u, v in w.items()
                       if _ID.fullmatch(str(u)) and isinstance(v, dict) and v.get("level") in KIND_LEVELS["doc"]}
                   for k, w in docs.items() if _DOC.fullmatch(str(k)) and isinstance(w, dict)},
           "seen": int(d.get("seen") or 0) if isinstance(d.get("seen"), (int, float)) else 0}
    out["doc"] = {k: w for k, w in out["doc"].items() if w}
    _cache[uid] = (m, out)
    return out


def _store(uid, d):
    with _lock:
        profiles._write(_file(uid), {"doc": d["doc"], "seen": d.get("seen", 0)})
        _cache.pop(uid, None)


def may(uid):
    """Teilen is released for this profile (and it is a profile: guests never)."""
    return bool(uid) and uid in profiles.user_ids() and features.allowed("teilen", uid)


def may_kind(kind, uid):
    return may(uid) and features.allowed(FEATURE[kind], uid)


def _name(uid):
    return (profiles.by_id(uid) or {}).get("name", "?")


def _count(what):
    day = time.strftime("%Y-%m-%d")
    if _today["day"] != day:
        _today.update(day=day, set=0, back=0)
    _today[what] += 1


# ---------------------------------------------------------------- documents (kept here)
def doc_offer(viewer, owner):
    """The single documents owner shares with viewer, while both may: a set of document ids (wissen._offer adds
    „Für alle“ to it). Empty when either may not."""
    if viewer == owner or not (may_kind("doc", viewer) and may_kind("doc", owner)):
        return frozenset()
    return frozenset(k for k, w in _load(owner)["doc"].items() if viewer in w)


def doc_ids(owner):
    """The owner's documents shared with at least one single profile."""
    return frozenset(_load(owner)["doc"])


def doc_owners(viewer):
    """The profiles that share single documents with viewer."""
    if not may_kind("doc", viewer):
        return []
    return [o for o in profiles.user_ids() if o != viewer and os.path.exists(_file(o)) and doc_offer(viewer, o)]


def _doc_put(owner, doc_id, to, level):
    import documents
    if not _DOC.fullmatch(doc_id or "") or not documents.doc_ready(owner, doc_id):
        raise KeyError(doc_id)
    d = _load(owner)
    d = {"doc": {k: dict(w) for k, w in d["doc"].items()}, "seen": d["seen"]}
    w = d["doc"].setdefault(doc_id, {})
    was = (w.get(to) or {}).get("level", "")
    if level:
        if to not in w and len(w) >= MAX_PER_ITEM:
            raise ValueError(f"shared with {MAX_PER_ITEM} profiles already")
        if doc_id not in _load(owner)["doc"] and len(d["doc"]) > MAX_ITEMS:
            raise ValueError(f"{MAX_ITEMS} documents shared already")
        w[to] = {"level": level, "t": int(time.time()) if was != level else (w.get(to) or {}).get("t", int(time.time()))}
    else:
        w.pop(to, None)
    d["doc"] = {k: v for k, v in d["doc"].items() if v}
    _store(owner, d)
    return was


# ---------------------------------------------------------------- the kinds, the same questions
def _people_doc(owner, item):
    w = _load(owner)["doc"].get(item, {})
    return {u: v["level"] for u, v in w.items()}


def _people_cal(owner, item):
    import calendars
    c = next((x for x in calendars.get(owner)["calendars"] if x["id"] == item), None)
    if c is None:
        raise KeyError(item)
    return {u: v for u, v in (c.get("shares") or {}).items() if v in LEVELS}


def _people_list(owner, item):
    import tasks
    return next(({u: v for u, v in sh.items() if v in LEVELS} for lid, _, sh in tasks.shared_by(owner) if lid == item), {})


PEOPLE = {"doc": _people_doc, "cal": _people_cal, "list": _people_list}


def _mine(uid):
    """What uid shares, every kind: [{"kind", "id", "name", "people": [{"id", "name", "level", "t"}]}]."""
    out = []
    if may_kind("doc", uid):
        import documents
        names = {d["id"]: d["name"] for d in documents.list_docs(uid)}
        d = _load(uid)
        if set(d["doc"]) - set(names):   # a deleted document is shared with nobody any more
            _store(uid, {"doc": {k: w for k, w in d["doc"].items() if k in names}, "seen": d["seen"]})
        for k, w in _load(uid)["doc"].items():
            if k in names:
                out.append({"kind": "doc", "id": k, "name": names[k],
                            "people": [{"id": u, "name": _name(u), "level": v["level"], "t": v["t"]} for u, v in w.items()]})
        for d in documents.list_shared(uid) if features.allowed("docshared", uid) else []:
            out.append({"kind": "doc", "id": d["id"], "name": d["name"], "all": True, "people": []})
    if may_kind("cal", uid):
        import calendars
        for c in calendars.get(uid)["calendars"]:
            sh = {u: v for u, v in (c.get("shares") or {}).items() if v in LEVELS}
            if sh:
                out.append({"kind": "cal", "id": c["id"], "name": c.get("name") or "Kalender",
                            "people": [{"id": u, "name": _name(u), "level": v, "t": 0} for u, v in sh.items()]})
    if may_kind("list", uid):
        import tasks
        for lid, lst, sh in tasks.shared_by(uid):
            out.append({"kind": "list", "id": lid, "name": lst.get("name") or lid,
                        "people": [{"id": u, "name": _name(u), "level": v, "t": 0} for u, v in sh.items() if v in LEVELS]})
    return out


def _theirs(uid):
    """What the others share with uid, every kind: [{"kind", "id", "name", "owner", "who", "level", "t", "all"}]."""
    out = []
    if may_kind("doc", uid):
        import documents
        import wissen
        for o in profiles.user_ids():
            if o == uid:
                continue
            offer = wissen._offer(uid, o)
            if not offer.all and not offer.ids:
                continue
            w = _load(o)["doc"]
            for d in documents.list_shared(o, offer):
                one = (w.get(d["id"]) or {}).get(uid)
                out.append({"kind": "doc", "id": d["id"], "name": d["name"], "owner": o, "who": _name(o),
                            "level": one["level"] if one else "see", "t": one["t"] if one else 0, "all": not one})
    if may_kind("cal", uid):
        import calendars
        for o, n, c, lvl in calendars.shared_to(uid):
            out.append({"kind": "cal", "id": c["id"], "name": calendars.shared_name(n, c), "owner": o, "who": n,
                        "level": lvl, "t": 0, "all": False})
    if may_kind("list", uid):
        import tasks
        for o, n, lst, lvl in tasks.shared_to(uid):
            out.append({"kind": "list", "id": f"{o}.{lst['id']}", "name": lst.get("name") or lst["id"], "owner": o, "who": n,
                        "level": lvl, "t": 0, "all": False})
    return sorted(out, key=lambda x: (-x["t"], x["kind"], x["name"].lower()))


def put(kind, owner, item, to, level):
    """Shares item of owner with the profile to ("see", "add") or takes it back (""): the kind's own way, with the
    same checks for every kind. Returns the level it had before. KeyError: no such item; ValueError: not allowed."""
    if kind not in KINDS:
        raise ValueError("no such kind")
    if level not in KIND_LEVELS[kind] + ("",):
        raise ValueError("level not possible for this kind")
    if to == owner or to not in profiles.user_ids():
        raise ValueError("no such other profile")
    if level and not may_kind(kind, to):
        raise ValueError("the other profile cannot use this (Funktionen)")
    if kind == "doc":
        was = _doc_put(owner, item, to, level)
    elif level:
        raise ValueError("calendars and lists are shared in their own dialog; here they are only taken back")
    elif kind == "cal":
        import calendars
        was = _people_cal(owner, item).get(to, "")
        calendars.set_share(owner, item, to, "")
    else:
        import tasks
        was = _people_list(owner, item).get(to, "")
        tasks.set_share(owner, item, to, "")
    _count("set" if level else "back")
    return was


# ---------------------------------------------------------------- the note to the other profile
async def tell(to, owner, kind):
    """One note to the other profile on a new share: at once, or counted into one after NOTE_GAP. Its words are
    fixed, with the owner's name only (the title stays on the page Ich → Geteilt)."""
    if not features.pref_on("teilenhinweis", to):
        print(f"geteilt: note skipped, switched off | {profiles.log_name(profiles.by_id(to))}", flush=True)
        return
    n = _note.setdefault(to, {"t": 0, "n": 0, "task": None})
    now = time.time()
    if now - n["t"] < NOTE_GAP:
        n["n"] += 1
        if n["task"] is None:
            n["task"] = asyncio.get_running_loop().create_task(_later(to, NOTE_GAP - (now - n["t"])))
        print(f"geteilt: note collected | {n['n']} waiting | {profiles.log_name(profiles.by_id(to))}", flush=True)
        return
    n["t"] = now
    await _send(to, f"{_name(owner)} hat etwas mit dir geteilt", WORD[kind])


async def _later(to, wait):
    await asyncio.sleep(max(1, wait))
    n = _note.get(to) or {}
    k, n["n"], n["task"], n["t"] = n.get("n", 0), 0, None, time.time()
    if k:
        await _send(to, f"{k} neue Sachen mit dir geteilt", "mehrere")


WORD = {"doc": "Dokument", "cal": "Kalender", "list": "Liste"}


async def _send(to, title, what):
    import push
    try:
        await push.send(to, title, f"{what} · Ich → Geteilt", tag="share")
    except Exception as e:   # the share stands, only the note did not go
        print(f"geteilt: note failed | {type(e).__name__} | {profiles.log_name(profiles.by_id(to))}", flush=True)


# ---------------------------------------------------------------- Live, Monitoring
_live = [0.0, {}]


def for_live(now=None):
    """How many single documents are shared, by how many profiles, and what changed today: numbers only."""
    now = time.time() if now is None else now
    if not features.admin_on("teilen"):
        return {"on": False}
    if 0 <= now - _live[0] < 30:
        return _live[1]
    n = owners = 0
    for u in profiles.user_ids():
        k = sum(len(w) for w in _load(u)["doc"].values()) if os.path.exists(_file(u)) else 0
        n, owners = n + k, owners + (1 if k else 0)
    day = time.strftime("%Y-%m-%d")
    today = (_today["set"], _today["back"]) if _today["day"] == day else (0, 0)
    _live[:] = [now, {"on": True, "docs": n, "owners": owners, "set": today[0], "back": today[1]}]
    return _live[1]


# ---------------------------------------------------------------- endpoints
router = APIRouter()


def _on(prof):
    if not may(prof["id"]):
        print(f"geteilt: refused, off | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(403, "Teilen ist aus (Funktionen → Teilen mit Profilen)")


@router.get("/api/profile/geteilt", dependencies=[Depends(assistant)])
async def shared_page(request: Request, prof=Depends(browser_profile)):
    """Ich → Geteilt: what the others share with this profile and what it shares; opening it marks all as seen."""
    _on(prof)
    uid = prof["id"]
    guard.limit(request, "geteilt", uid)
    theirs = await asyncio.to_thread(_theirs, uid)
    mine = await asyncio.to_thread(_mine, uid)
    d = _load(uid)
    seen = d["seen"]
    new = sum(1 for x in theirs if x["t"] > seen)
    if new or not seen:
        _store(uid, {"doc": d["doc"], "seen": int(time.time())})
    kinds = [k for k in KINDS if may_kind(k, uid)]
    print(f"geteilt: page | {len(theirs)} theirs | {len(mine)} mine | {new} new | {profiles.log_name(prof)}", flush=True)
    return {"theirs": [dict(x, new=x["t"] > seen) for x in theirs], "mine": mine, "new": new, "kinds": kinds,
            "note": features.pref_on("teilenhinweis", uid)}


def _doc_name(owner, item):
    import documents
    if not documents.doc_ready(owner, item):
        raise KeyError(item)
    return next(d["name"] for d in documents.list_docs(owner) if d["id"] == item)


@router.get("/api/profile/teilen/{kind}/{item}", dependencies=[Depends(assistant)])
async def dialog(kind: str, item: str, request: Request, prof=Depends(browser_profile)):
    """The common dialog: the item, every other profile with its level, and „Alle Profile“ where the kind has it.
    Stufe 1: documents; calendars and lists keep their own dialog for now (Listen and Kalender pages)."""
    _on(prof)
    uid = prof["id"]
    guard.limit(request, "geteilt", uid)
    if kind != "doc" or not may_kind(kind, uid):
        raise HTTPException(404, "no such kind")
    try:
        name = await asyncio.to_thread(_doc_name, uid, item[:40])
        have = await asyncio.to_thread(PEOPLE[kind], uid, item[:40])
    except KeyError:
        raise HTTPException(404, "no such item")
    people = [{"id": p["id"], "name": p["name"], "level": have.get(p["id"], ""), "can": may_kind(kind, p["id"])}
              for p in profiles.names() if p["id"] != uid]
    out = {"kind": kind, "id": item[:40], "name": name, "levels": list(KIND_LEVELS[kind]), "people": people, "all": None}
    if features.allowed("docshared", uid):
        import documents
        out["all"] = documents.is_shared(uid, item[:40])
    return out


@router.put("/api/profile/teilen/{kind}/{item}", dependencies=[Depends(assistant)])
async def share(kind: str, item: str, request: Request, prof=Depends(secret_profile)):
    """Shares one item with one profile or takes it back: {"to", "level"}; for documents also {"all": bool} („Für
    alle“, the old way). Only the own browser login with the code (Bestätigen, stufen.LIST), never a device key."""
    _on(prof)
    uid = prof["id"]
    guard.limit(request, "teilen", uid)
    body = await json_body(request, 1024)
    if kind not in KINDS or not may_kind(kind, uid):
        print(f"geteilt: refused, kind off | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(404, "no such kind")
    item = item[:40]
    if kind == "doc" and isinstance(body.get("all"), bool):
        import documents
        if not features.allowed("docshared", uid):
            print(f"geteilt: refused, all off | {profiles.log_name(prof)}", flush=True)
            raise HTTPException(403, "„Für alle“ ist aus (Funktionen → Gemeinsame Dokumente)")
        if not documents.set_shared(uid, item, body["all"]):
            print(f"geteilt: refused, no such item | doc | {profiles.log_name(prof)}", flush=True)
            raise HTTPException(404, "no such item")
        _count("set" if body["all"] else "back")
        print(f"geteilt: all {'set' if body['all'] else 'taken back'} | doc | {profiles.log_name(prof)}", flush=True)
        return await dialog(kind, item, request, prof)
    to, level = str(body.get("to") or "")[:40], str(body.get("level") or "")[:8]
    try:
        was = await asyncio.to_thread(put, kind, uid, item, to, level)
    except KeyError:
        print(f"geteilt: refused, no such item | {kind} | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(404, "no such item")
    except ValueError as e:
        print(f"geteilt: refused | {kind} | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(400, str(e))
    print(f"geteilt: {'set ' + level if level else 'taken back'} | {kind} | {profiles.log_name(prof)}", flush=True)
    if level and not was:
        await tell(to, uid, kind)
    return await dialog(kind, item, request, prof) if kind == "doc" else {"ok": True}
