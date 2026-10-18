"""Ordner auslassen (plan plaene/ordner-auslassen.md; Dominik 2026-10-18 "1a 2a 3a 4a 5a").

A profile keeps one list of folders the Spark never reads: single folders at one of its places, and names that are
left out wherever they occur ("Archiv", "Alt*"). It counts for every source with folders: the Wissensordner and the
Haushaltsordner an admin profile chose (its list counts there; Stufe A), the reMarkable folders and the Begleiter's
folder "Spark-Wissen" on the PC (Stufe B).

    USERS_DIR/<uid>/auslassen.json   {"folders": [{"ort", "path", "t"}], "names": ["Archiv", "Alt*"]}
    ort = the place: a nas.py connection id, "rm" (reMarkable) or "pc" (the Begleiter's folder, on every PC of
          the profile); path = "/a/b" there (nasquelle.clean_path)

The Begleiter reports the sub folders of its folder (POST /api/desk/ordner, kept in memory only, PC_DIRS) so the
tree can show them, sends the folder of each file it hands over (documents.place, origin "pc"), and gets the list
with its config: it sends nothing from a left-out folder. The panel refuses such a file too (409).

Rules (fixed in the panel, never decided by the model):
- A folder is left out with everything below it. A name rule counts for every folder in the path, case does not
  matter, a "*" at the end means "begins with"; no other patterns, so nothing unexpected matches.
- Hidden and system folders stay left out as before (nasquelle.SKIP_DIRS); they are shown, not changeable.
- What was read from a folder that is now left out leaves the search, Ich → Dokumente, "Erst lokal" and the
  Wissensbuch at once (documents.on_gone with reason "ausgelassen"). Nothing changes at the place.
- Letting a folder in again makes its Wissensordner due at once, so it is read anew; the reMarkable reads it at
  its next comparison, the Begleiter sends its files again (it forgets what it sent from a left-out folder).
- No switch of its own: it only narrows what a source reads (5a). The list is the profile's own data: visible and
  changeable also while the admin blocks the Wissensordner. Guests have no profile, so no list.

Logs → Diagnose, area "Wissen": lines "auslassen: ..." with fixed words and numbers, never a path or a name.
"""
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import core
import guard
import profiles
from core import browser_profile

router = APIRouter()

FILE = "auslassen.json"
MAX_FOLDERS = 200
MAX_NAMES = 50
ORT = re.compile(r"[0-9a-f]{6}|rm|pc")
PLACE = {"rm": "reMarkable", "pc": "PC · Spark-Wissen"}
MAX_PC_DIRS = 2000
PC_DIRS = {}                  # uid -> sorted folder paths below the Begleiter's folder, as last reported (memory only)
NAME = re.compile(r"[^\x00-\x1f\x7f/\\*]{1,80}\*?")
_lock = threading.RLock()


def _log_name(uid):
    return profiles.log_name(profiles.by_id(uid))


# ---------------------------------------------------------------- the list
def clean_name(v):
    """A name rule: 1 to 80 characters without slashes or control characters, a "*" only at the end."""
    v = str(v or "").strip()
    if not NAME.fullmatch(v) or v.strip("*").strip() in ("", ".", ".."):
        raise ValueError("bad name")
    return v


def clean_folder(ort, path):
    import nasquelle
    if not ORT.fullmatch(str(ort or "")):
        raise ValueError("bad place")
    p = nasquelle.clean_path(path)
    if not p:
        raise ValueError("the place itself")
    return str(ort), p


def load(uid):
    if not uid:
        return {"folders": [], "names": []}
    with _lock:
        raw = _json(uid)
    folders, names = [], []
    for f in raw.get("folders") or [] if isinstance(raw.get("folders"), list) else []:
        try:
            ort, p = clean_folder((f or {}).get("ort"), (f or {}).get("path"))
        except (ValueError, AttributeError):
            continue
        if not any(x["ort"] == ort and x["path"] == p for x in folders):
            folders.append({"ort": ort, "path": p, "t": int((f or {}).get("t") or 0)})
    for n in raw.get("names") or [] if isinstance(raw.get("names"), list) else []:
        try:
            n = clean_name(n)
        except ValueError:
            continue
        if n.casefold() not in [x.casefold() for x in names]:
            names.append(n)
    return {"folders": folders[:MAX_FOLDERS], "names": names[:MAX_NAMES]}


def _json(uid):
    import json
    try:
        with open(profiles._path(uid, FILE)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(uid, d):
    with _lock:
        profiles._write(profiles._path(uid, FILE), {"folders": d["folders"][:MAX_FOLDERS], "names": d["names"][:MAX_NAMES]})


def name_hit(names, seg):
    """The name rule a folder name falls under, or ""."""
    s = seg.casefold()
    for n in names:
        k = n.casefold()
        if (s.startswith(k[:-1]) if k.endswith("*") else s == k):
            return n
    return ""


def why(uid, ort, path, d=None):
    """Why the folder "path" at place "ort" is left out for this profile: "ordner", "name" or ""."""
    if not uid:
        return ""
    d = load(uid) if d is None else d
    p = path if path.startswith("/") else "/" + path
    if any(f["ort"] == ort and (p == f["path"] or p.startswith(f["path"] + "/")) for f in d["folders"]):
        return "ordner"
    if d["names"] and any(name_hit(d["names"], seg) for seg in p.split("/") if seg):
        return "name"
    return ""


def checker(uid, ort, root):
    """For nasquelle.walk: rel (below root) -> left out? The list is read once per walk."""
    d = load(uid)
    if not d["folders"] and not d["names"]:
        return lambda rel: False
    base = root.rstrip("/")
    return lambda rel: bool(why(uid, ort, f"{base}/{rel}" if rel else base or "/", d))


def add_folders(uid, items):
    """Folders taken over from elsewhere (nasquelle's former per-folder "skip" field): [(ort, path)]."""
    with _lock:
        d = load(uid)
        n = 0
        for ort, p in items:
            try:
                ort, p = clean_folder(ort, p)
            except ValueError:
                continue
            if len(d["folders"]) < MAX_FOLDERS and not any(x["ort"] == ort and x["path"] == p for x in d["folders"]):
                d["folders"].append({"ort": ort, "path": p, "t": int(time.time())})
                n += 1
        if n:
            _save(uid, d)
    return n


def counts(uid):
    d = load(uid)
    return len(d["folders"]), len(d["names"])


# ---------------------------------------------------------------- what it does
def _sources(uid):
    """[(store, source)]: the profile's Wissensordner and the Haushaltsordner it chose (its list counts there)."""
    import nasquelle
    return [(uid, s) for s in nasquelle.sources(uid)] + \
           [(nasquelle.HAUS, s) for s in nasquelle.sources(nasquelle.HAUS) if s.get("owner") == uid]


def _rm_folder(items, rid):
    import remarkable
    p = remarkable.path_of(items, rid)
    return "/" + p.rsplit("/", 1)[0] if p and "/" in p else ""


def affected(uid, d=None):
    """[(kind, store, key, document id)] of what was read and now falls under the list: kind "nas" (key: the
    Wissensordner and the file hash), "rm" (key: the notebook) or "pc" (key: None)."""
    import documents
    import nasquelle
    import remarkable
    d = load(uid) if d is None else d
    out = []
    for store, s in _sources(uid):
        for h, x in nasquelle.state(store, s["id"])["files"].items():
            rel = x.get("p", "")
            folder = s["path"] + "/" + rel.rsplit("/", 1)[0] if "/" in rel else s["path"]
            if why(uid, s["nas"], folder or "/", d):
                out.append(("nas", store, (s["id"], h), x.get("d") or ""))
    rm = remarkable.load(uid)
    if rm["docs"]:
        items = remarkable.library(uid)
        for rid, st in rm["docs"].items():
            f = _rm_folder(items, rid)
            if f and why(uid, "rm", f, d):
                out.append(("rm", uid, rid, st.get("doc") or ""))
    for doc in documents.list_docs(uid):
        if doc.get("source") == "begleiter" and doc.get("place") and why(uid, "pc", doc["place"], d):
            out.append(("pc", uid, None, doc["id"]))
    return out


def apply(uid):
    """Takes what falls under the list out of the search now. Returns the number of documents."""
    import documents
    import nasquelle
    import remarkable
    hit = affected(uid)
    gone, rids = {}, []
    for kind, store, key, doc in hit:
        if kind == "nas":
            st = nasquelle.state(store, key[0])
            st["files"].pop(key[1], None)
            nasquelle._put_state(store, key[0], st)
        elif kind == "rm":
            rids.append(key)
        if doc and documents.delete(store, doc):
            gone.setdefault(store, []).append(doc)
    if rids:                         # the comparison reads only what is wanted (remarkable.wanted asks the list)
        rm = remarkable.load(uid)
        for rid in rids:
            rm["docs"].pop(rid, None)
        remarkable.save(uid, rm)
    for store, ids in gone.items():
        documents.on_gone(store, ids, "ausgelassen")
    return sum(len(v) for v in gone.values())


def _due_again(uid, ort):
    """Letting a folder in: its Wissensordner at that place read anew at the next round."""
    import nasquelle
    for store, s in _sources(uid):
        if ort is None or s["nas"] == ort:
            st = nasquelle.state(store, s["id"])
            st["last"] = None
            nasquelle._put_state(store, s["id"], st)


def _rm_on(uid):
    import features
    import remarkable
    return features.allowed("remarkable", uid) and bool(remarkable.load(uid).get("token"))


def view(uid):
    import nas
    import nasquelle
    d = load(uid)
    places = dict({c["id"]: c.get("name") or c.get("kind", "") for c in nas.load(uid)}, **PLACE)
    srcs = [{"id": s["id"], "nas": s["nas"], "path": s["path"] or "/", "place": places.get(s["nas"], ""),
             "haus": store == nasquelle.HAUS, "tree": nasquelle.allowed(uid)} for store, s in _sources(uid)]
    srcs += [{"id": o, "nas": o, "path": "/", "place": PLACE[o], "haus": False, "tree": True}
             for o, on in (("rm", _rm_on(uid)), ("pc", uid in PC_DIRS)) if on]
    return {"folders": [dict(f, place=places.get(f["ort"], "")) for f in d["folders"]], "names": d["names"],
            "max_folders": MAX_FOLDERS, "max_names": MAX_NAMES, "sources": srcs, "tree": any(x["tree"] for x in srcs),
            "always": ["Versteckte Ordner (.…)", "@eaDir", "#recycle", "#snapshot", "$RECYCLE.BIN", "System Volume Information", "lost+found"]}


# ---------------------------------------------------------------- routes (own data, browser login only)
@router.get("/api/profile/auslassen")
def get_mine(request: Request, prof=Depends(browser_profile)):
    guard.limit(request, "storage", prof["id"])
    return view(prof["id"])


def _target(uid, body):
    """("name", rule) or ("ordner", (ort, path)) from a request body; the place must be one of the profile's."""
    import nas
    try:
        if body.get("name") is not None:
            return "name", clean_name(body["name"])
        ort, p = clean_folder(body.get("ort"), body.get("path"))
    except ValueError:
        raise HTTPException(400, "Ungültiger Ordner oder Name.")
    if ort not in PLACE and not nas.find(uid, ort):
        raise HTTPException(404, "no such place")
    return "ordner", (ort, p)


def _dirs(uid, ort):
    """Every folder known at "rm" (the reMarkable listing) or "pc" (what the Begleiter reported): ["/a", "/a/b"]."""
    if ort == "pc":
        return PC_DIRS.get(uid, [])
    import remarkable
    items = remarkable.library(uid)
    out = set()
    for i, it in items.items():
        p = remarkable.path_of(items, i) if it.get("folder") else None
        if p:
            out.add("/" + p)
    return sorted(out)


@router.get("/api/profile/auslassen/tree")
def tree(request: Request, ort: str = "", path: str = "", prof=Depends(browser_profile)):
    """The sub folders of one folder at the reMarkable or in the Begleiter's folder (from what the Spark knows,
    nothing is fetched); NAS folders: /api/profile/nasquelle/tree."""
    guard.limit(request, "storage", prof["id"])
    uid = prof["id"]
    if ort not in PLACE:
        raise HTTPException(400, "ort: rm or pc")
    if ort == "rm" and not _rm_on(uid):
        raise HTTPException(403, "reMarkable ist nicht verbunden.")
    import nasquelle
    try:
        here = nasquelle.clean_path(path)
    except ValueError:
        raise HTTPException(400, "invalid folder")
    pre = here + "/"
    kids = sorted({p[len(pre):].split("/")[0] for p in _dirs(uid, ort) if p.startswith(pre)}, key=str.lower)
    mine = load(uid)
    out = {n: w for n in kids[:500] if (w := why(uid, ort, f"{here}/{n}", mine))}
    print(f"auslassen: ordnerliste | {ort} | {len(kids)} ordner | {_log_name(uid)}", flush=True)
    return {"path": here or "/", "dirs": kids[:500], "more": len(kids) > 500, "out": out}


@router.post("/api/profile/auslassen")
async def add(request: Request, prof=Depends(browser_profile)):
    """{"ort", "path"} or {"name"}; with "probe": true only how many documents would leave the search."""
    guard.limit(request, "storage", prof["id"])
    uid = prof["id"]
    body = await core.json_body(request, 4096)
    kind, what = _target(uid, body)
    with _lock:
        d = load(uid)
        if kind == "name":
            new = {"folders": d["folders"], "names": d["names"] + [what]}
            known = what.casefold() in [x.casefold() for x in d["names"]]
            full = len(d["names"]) >= MAX_NAMES
        else:
            new = {"folders": d["folders"] + [{"ort": what[0], "path": what[1], "t": int(time.time())}], "names": d["names"]}
            known = any(x["ort"] == what[0] and x["path"] == what[1] for x in d["folders"])
            full = len(d["folders"]) >= MAX_FOLDERS
        if body.get("probe") is True:
            n = sum(1 for x in affected(uid, new) if x[3])
            print(f"auslassen: probe | {kind} | {n} dokumente | {_log_name(uid)}", flush=True)
            return {"docs": n, "known": known}
        if known:
            print(f"auslassen: schon da | {kind} | {_log_name(uid)}", flush=True)
            raise HTTPException(409, "Steht schon in der Liste.")
        if full:
            print(f"auslassen: abgelehnt | {kind} | voll | {_log_name(uid)}", flush=True)
            raise HTTPException(400, f"Höchstens {MAX_NAMES if kind == 'name' else MAX_FOLDERS} Einträge.")
        _save(uid, new)
    n = apply(uid)
    guard.log("auslassen_add", detail=kind)
    print(f"auslassen: ausgelassen | {kind} | {n} dokumente raus | {_log_name(uid)}", flush=True)
    return {"ok": True, "removed": n}


@router.delete("/api/profile/auslassen")
def remove(request: Request, ort: str = "", path: str = "", name: str = "", prof=Depends(browser_profile)):
    """?ort=&path= or ?name=: let it in again; the Wissensordner concerned read it anew at the next round."""
    guard.limit(request, "storage", prof["id"])
    uid = prof["id"]
    with _lock:
        d = load(uid)
        if name:
            kind = "name"
            keep = [x for x in d["names"] if x.casefold() != name.strip().casefold()]
            hit = len(keep) != len(d["names"])
            d["names"], ort_ = keep, None
        else:
            kind = "ordner"
            try:
                ort_, p = clean_folder(ort, path)
            except ValueError:
                print(f"auslassen: zulassen abgelehnt | ungültig | {_log_name(uid)}", flush=True)
                raise HTTPException(400, "Ungültiger Ordner.")
            keep = [x for x in d["folders"] if not (x["ort"] == ort_ and x["path"] == p)]
            hit = len(keep) != len(d["folders"])
            d["folders"] = keep
        if not hit:
            print(f"auslassen: zulassen | {kind} | nicht gefunden | {_log_name(uid)}", flush=True)
            raise HTTPException(404, "Steht nicht in der Liste.")
        _save(uid, d)
    _due_again(uid, ort_)
    guard.log("auslassen_remove", detail=kind)
    print(f"auslassen: zugelassen | {kind} | {_log_name(uid)}", flush=True)
    return {"ok": True}


# ---------------------------------------------------------------- the Begleiter (begleiter.py)
def for_desk(uid):
    """The list as the Begleiter gets it with its config: names, and the folders below "Spark-Wissen" ("a/b")."""
    d = load(uid)
    return {"names": d["names"], "folders": [f["path"][1:] for f in d["folders"] if f["ort"] == "pc"]}


def pc_dirs(uid, dirs):
    """The sub folders the Begleiter reported (paths below its folder); kept in memory for the tree only."""
    import nasquelle
    out = set()
    for x in dirs[:MAX_PC_DIRS] if isinstance(dirs, list) else []:
        try:
            p = nasquelle.clean_path(x) if isinstance(x, str) else ""
        except ValueError:
            continue
        if p:
            out.add(p)
    PC_DIRS[uid] = sorted(out)
    return len(out)
