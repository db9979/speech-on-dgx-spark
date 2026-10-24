"""Alle Mails eines Ordners einordnen (Dominik 2026-10-24 „1-3“, part of „Mails ordnen“, no switch of its own): from the
„⋯“ of a folder on the page E-Mail (the inbox, the archive or an own folder) every mail in it, down to the oldest, is
looked at once by the fixed rules and put into its folder, not only the last days like „Altlasten“ (tidy.backlog_scan).

- Who decides, per mail, the first that fits: the profile's own mail rules (mailregeln.first, only their folder), then,
  where „Mails aufräumen“ is on for that mailbox, its stages 1 to 3 (protected, its rules, header signs; tidy.decide,
  tidy.action == "move"). Never the language model: a mail no rule knows stays where it is, so does one whose folder
  is the folder itself or one no message may go to (postfach._targets: never trash, junk, sent or drafts).
- First a proposal (scan, in the background, PACK mails a step, at most ALL_MAX): how many go into which folder and
  how many stay. Nothing moves before „Verschieben“ (go, with the code like any bulk change), which moves in packages
  of MOVE_STEP; „Abbrechen“ stops both after the step running. The proposal lives in memory only and goes with a
  restart; a server that numbered the folder anew since (UIDVALIDITY) moves nothing.
- „Rückgängig“ (back) brings every mail of the last run back into its folder by its Message-ID; the run (account,
  folder, target folders, Message-IDs, at most UNDO_MAX) lies sealed in users/<id>/mail-einordnen.bin (vorrat.seal,
  600) for UNDO_DAYS days; without a key only in memory. Never a deletion, never a flag.
- One run per profile and at most JOBS at once on the Spark; between two steps speech goes first (vorrang.hold).
- Journal lines carry fixed words and numbers, the profile only as profiles.log_name (never a folder, sender or
  subject); Live (node E-Mail) shows runs and mails moved today, numbers only.
"""
import imaplib
import json
import os
import threading
import time

import features
import mail
import mailregeln
import notaus
import profiles
import tidy
import vorrang
from common import DayCounter, write_json

FILE = "mail-einordnen.bin"
PACK = 2000          # mails whose headers one step of the proposal reads
ALL_MAX = 50000      # mails of one folder a proposal looks at (the newest)
MOVE_STEP = 100      # mails one MOVE command takes
UNDO_MAX = 50000     # Message-IDs a run keeps for „Rückgängig“
UNDO_DAYS = 30
JOBS = 2             # runs at once on the Spark
HEAD = " ".join(dict.fromkeys((tidy.HEAD_FIELDS + " " + mailregeln.HEAD).split()))
STATES = ("scan", "ready", "move", "back", "done", "stopped", "error")

_lock = threading.Lock()
_jobs = {}           # uid -> the run: {state, account, folder, looked, total, stays, moved, plan, validity, stop, err}
_undo_mem = {}      # uid -> the last run when nothing can be sealed here
_count = DayCounter(laeufe=0, verschoben=0, zurueck=0)


def _who(uid):
    return profiles.log_name(profiles.by_id(uid))


def _file(uid):
    return profiles._path(uid, FILE)


def _undo(uid):
    d = _undo_mem.get(uid)
    if d is None:
        import vorrat
        try:
            with open(_file(uid), encoding="utf-8") as f:
                d = json.loads(vorrat.unseal(json.load(f).get("data", ""), f"{uid}/{FILE}") or b"null")
        except (OSError, ValueError, AttributeError):
            d = None
    if not isinstance(d, dict) or time.time() - d.get("t", 0) > UNDO_DAYS * 86400 or not isinstance(d.get("moved"), dict):
        return None
    return d


def _undo_save(uid, d):
    """The last run for „Rückgängig“, sealed; None drops it."""
    import vorrat
    _undo_mem.pop(uid, None)
    if d is None:
        try:
            os.remove(_file(uid))
        except OSError:
            pass
        return
    sealed = vorrat.seal(json.dumps(d).encode(), f"{uid}/{FILE}")
    if sealed is None:
        _undo_mem[uid] = d          # no key here: only until the next restart
        return
    write_json(_file(uid), {"v": 1, "data": sealed}, mode=0o600, dir_mode=0o700)


def _acct(uid, account_id):
    acct = next((a for a in mail.get(uid)["accounts"] if a["id"] == account_id), None)
    if not acct:
        raise LookupError("unknown mailbox")
    return acct


def public(uid):
    """What the page shows: the run's state and numbers, the folder it is about; never a sender or subject."""
    j = _jobs.get(uid)
    u = _undo(uid)
    out = {"undo": {"n": sum(len(v) for v in u["moved"].values()), "folder": u["folder"], "account": u["account"],
                    "t": u["t"]} if u else None}
    if j:
        out.update({k: j[k] for k in ("kind", "state", "account", "folder", "looked", "total", "stays", "moved", "err")},
                   by=sorted(([f, len(v)] for f, v in j["plan"].items()), key=lambda x: -x[1]), cut=j["total"] > ALL_MAX)
    return out


def _decider(uid, acct):
    """f(header message) -> target folder or "": the profile's mail rules first, then the tidying stages 1 to 3."""
    rules = [r for r in mailregeln.load(uid)["rules"] if r.get("on", True) and r["then"].get("folder")]
    d = tidy.state(uid)
    use_tidy = features.allowed("tidy", uid) and tidy.acct_state(d, acct["id"])["mode"] != "off"

    def target(msg):
        r = mailregeln.first(rules, mailregeln.head(msg), acct["id"])
        if r:
            return r["then"]["folder"]
        if not use_tidy:
            return ""
        h = tidy.head(msg)
        cat, _, stage = tidy.decide(d, acct["id"], h, acct.get("user", ""))
        if stage == 4 or tidy.action(d, cat, stage) != "move":
            return ""
        if stage != 2 and d["kept"].get(h["sender"], 0) >= tidy.KEPT_GUARD:
            return ""
        return tidy.folder_of(d, cat)
    return target, d


def start(uid, account_id, folder):
    """Starts the proposal for every mail of one folder in the background; the page asks for public() after."""
    import postfach
    notaus.stop("aktion", uid)
    acct = _acct(uid, account_id)
    with tidy.Box(acct) as box:
        src = postfach._source(box, str(folder or "INBOX"), True)
    with _lock:
        j = _jobs.get(uid)
        if j and j["state"] in ("scan", "move", "back"):
            raise ValueError("a run is going already; wait for it or stop it")
        if sum(1 for x in _jobs.values() if x["state"] in ("scan", "move", "back")) >= JOBS:
            raise ValueError("the Spark sorts other mailboxes right now; please try again in a few minutes")
        _jobs[uid] = {"kind": "sort", "state": "scan", "account": acct["id"], "folder": src, "looked": 0, "total": 0,
                      "stays": 0, "moved": 0, "plan": {}, "validity": "", "stop": False, "err": ""}
    _count.bump("laeufe")
    threading.Thread(target=_scan, args=(uid, acct, src), daemon=True, name="einordnen").start()
    print(f"mail: sort folder started | {_who(uid)}", flush=True)
    return public(uid)


def _scan(uid, acct, src):
    import postfach
    j = _jobs[uid]
    try:
        target, d = _decider(uid, acct)
        with tidy.Box(acct, d) as box:
            targets, _ = postfach._targets(box)
            allowed = set(targets) | {box.name(p) for p in box.targets}
            j["validity"] = box.select(src)
            uids = sorted(box.search("ALL"), reverse=True)
            j["total"] = len(uids)
            for i in range(0, min(len(uids), ALL_MAX), PACK):
                if j["stop"]:
                    break
                vorrang.hold("Mail einordnen")
                part = uids[i:i + PACK]
                heads = box.headers(part, HEAD)
                for u in part:
                    msg = heads.get(u)
                    f = target(msg) if msg is not None else ""
                    f = box.name(f) if f and "/" in f and f not in box.boxes else f
                    if f and f != src and f in allowed:
                        j["plan"].setdefault(f, []).append(u)
                    else:
                        j["stays"] += 1
                j["looked"] += len(part)
        j["state"] = "stopped" if j["stop"] else "ready"
        n = sum(len(v) for v in j["plan"].values())
        print(f"mail: sort folder proposal | {j['looked']} looked, {n} to move, {j['stays']} stay | {_who(uid)}", flush=True)
    except Exception as e:
        j["state"], j["err"] = "error", "not reachable" if isinstance(e, (OSError, imaplib.IMAP4.error)) else "failed"
        print(f"mail: sort folder proposal failed ({type(e).__name__}) | {_who(uid)}", flush=True)


def go(uid):
    """„Verschieben“: the proposal is carried out in the background, package by package."""
    notaus.stop("aktion", uid)
    with _lock:
        j = _jobs.get(uid)
        if not j or j["state"] != "ready" or not j["plan"]:
            raise LookupError("no proposal to carry out")
        j["state"], j["stop"] = "move", False
    acct = _acct(uid, j["account"])
    threading.Thread(target=_move, args=(uid, acct), daemon=True, name="einordnen").start()
    print(f"mail: sort folder move started | {_who(uid)}", flush=True)
    return public(uid)


def _move(uid, acct):
    import postfach
    j = _jobs[uid]
    moved = {}
    try:
        d = tidy.state(uid)
        with tidy.Box(acct, d) as box:
            targets, _ = postfach._targets(box)
            if box.select(j["folder"], write=True) != j["validity"]:
                raise ValueError("renumbered")
            for f, uids in j["plan"].items():
                if j["stop"]:
                    break
                if f not in targets:
                    f = box.ensure(next(p for p in box.targets if box.name(p) == f))   # a tidying folder not made yet
                for i in range(0, len(uids), MOVE_STEP):
                    if j["stop"]:
                        break
                    vorrang.hold("Mail einordnen")
                    part = uids[i:i + MOVE_STEP]
                    present = set(box.search("UID", ",".join(map(str, part))))
                    part = [u for u in part if u in present]
                    if not part:
                        continue
                    mids = [tidy.clean_mid(m.get("Message-ID")) for m in box.headers(part, "MESSAGE-ID").values()]
                    postfach._move(box, part, f)
                    moved.setdefault(f, []).extend(m for m in mids if m)
                    j["moved"] += len(part)
        j["state"] = "stopped" if j["stop"] else "done"
        ok = True
    except Exception as e:
        j["state"], j["err"] = "error", ("renumbered" if str(e) == "renumbered" else
                                         "not reachable" if isinstance(e, (OSError, imaplib.IMAP4.error)) else "failed")
        ok = False
        print(f"mail: sort folder move failed ({type(e).__name__}) | {_who(uid)}", flush=True)
    j["plan"] = {}
    if moved:
        keep, n = {}, 0
        for f, ms in moved.items():
            keep[f] = ms[:max(0, UNDO_MAX - n)]
            n += len(keep[f])
        _undo_save(uid, {"t": int(time.time()), "account": j["account"], "folder": j["folder"], "moved": keep})
        mail.changed(uid, "", "back")
    _count.bump("verschoben", j["moved"])
    if ok:
        print(f"mail: sort folder moved | {j['moved']} | {_who(uid)}", flush=True)


def back(uid):
    """„Rückgängig“: every mail of the last run back into the folder it came from (in the background)."""
    notaus.stop("aktion", uid)
    u = _undo(uid)
    if not u:
        raise LookupError("nothing to bring back")
    acct = _acct(uid, u["account"])
    with _lock:
        j = _jobs.get(uid)
        if j and j["state"] in ("scan", "move", "back"):
            raise ValueError("a run is going already; wait for it or stop it")
        _jobs[uid] = {"kind": "back", "state": "back", "account": u["account"], "folder": u["folder"], "looked": 0,
                      "total": sum(len(v) for v in u["moved"].values()), "stays": 0, "moved": 0, "plan": {},
                      "validity": "", "stop": False, "err": ""}
    threading.Thread(target=_back, args=(uid, acct, u), daemon=True, name="einordnen").start()
    print(f"mail: sort folder back started | {_who(uid)}", flush=True)
    return public(uid)


def _back(uid, acct, u):
    import postfach
    j = _jobs[uid]
    try:
        with tidy.Box(acct) as box:
            home = postfach._source(box, u["folder"], True)
            left = {}
            for f, mids in u["moved"].items():
                if f not in box.boxes:
                    continue
                box.select(f, write=True)
                for i in range(0, len(mids), MOVE_STEP):
                    if j["stop"]:
                        left.setdefault(f, []).extend(mids[i:])
                        break
                    vorrang.hold("Mail einordnen")
                    part = mids[i:i + MOVE_STEP]
                    hits = [h for m in part for h in box.find_mid(m)[:1]]
                    if hits:
                        postfach._move(box, hits, home)
                    j["moved"] += len(hits)
                    j["looked"] += len(part)
        _undo_save(uid, dict(u, moved=left) if left else None)
        j["state"] = "stopped" if j["stop"] else "done"
        print(f"mail: sort folder back | {j['moved']} | {_who(uid)}", flush=True)
    except Exception as e:
        j["state"], j["err"] = "error", "not reachable" if isinstance(e, (OSError, imaplib.IMAP4.error)) else "failed"
        print(f"mail: sort folder back failed ({type(e).__name__}) | {_who(uid)}", flush=True)
    _count.bump("zurueck", j["moved"])
    if j["moved"]:
        mail.changed(uid, "", "back")


def stop(uid):
    """„Abbrechen“ while a run goes (it stops after the step running), „Verwerfen“ of a proposal."""
    j = _jobs.get(uid)
    if not j:
        print(f"mail: sort folder stop, nothing running | {_who(uid)}", flush=True)
        return public(uid)
    if j["state"] in ("scan", "move", "back"):
        j["stop"] = True
        print(f"mail: sort folder stopping | {_who(uid)}", flush=True)
    else:
        _jobs.pop(uid, None)
        print(f"mail: sort folder dropped | {_who(uid)}", flush=True)
    return public(uid)


def forget(uid):
    """A profile that is deleted or exports nothing more: its run and its „Rückgängig“ go."""
    j = _jobs.pop(uid, None)
    if j:
        j["stop"] = True
    _undo_save(uid, None)


def for_live():
    """Zustand → Live, node E-Mail: runs going now, runs and mails moved today (numbers only)."""
    c = _count.counts()
    return {"going": sum(1 for x in _jobs.values() if x["state"] in ("scan", "move", "back")), "runs": c["laeufe"],
            "moved": c["verschoben"], "back": c["zurueck"]}
