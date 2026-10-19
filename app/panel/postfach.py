"""Mails ordnen auf der Seite E-Mail (plan kalender-mail Stufe 2, function "Mails ordnen", chat.mail_manage, off):
the profile marks a message of its inbox as read or unread, archives it or moves it into one of its own folders,
and takes that back right after. Writing to the mailbox knows exactly these four things:

  - the flag \\Seen on one message of the inbox (UID STORE)
  - one message from the inbox into the archive folder (the server's \\Archive folder, else "Archive"/"Archiv")
    or into an ordinary folder of the mailbox
  - the same message back from there into the inbox (found again by its Message-ID)
  - the flag \\Flagged („Markieren“) on one or more messages of a folder
  - folders (Mailclient Stufe A, Dominik 2026-10-19 „1a“): every folder of every mailbox listed and read like the
    inbox (EXAMINE, PEEK); an own folder created, renamed or, when it is empty and has no folders inside, removed.
    Folders of the mail program (inbox, sent, drafts, trash, junk, archive) and the folders of „Mails aufräumen“
    (tidy.py, renamed there) are never renamed or removed.
  - nothing else: never into the trash, the junk, the sent or the drafts folder, never a message deleted

A button on the page is the person's own yes. The connection is tidy.Box (netguard.USER, TLS only); MOVE, or COPY
and then UID EXPUNGE of exactly the confirmed original where MOVE is missing (iCloud). Logs carry fixed words and
the profile's log name only, never a sender, a subject or a folder.
"""
import imaplib
import re
import threading
import time

import mail
import notaus
import profiles
import tidy

ACTIONS = ("read", "unread", "flag", "unflag", "archive", "move", "back")
MANY = 50          # messages one request of the page changes at most (Mehrfachauswahl)
TREE_MAX = 80      # folders per mailbox the page lists
LIST_MAX = 50      # messages of a folder the page lists (newest first)
TREE_SECONDS = 60  # the folder tree with its unread counts is kept this long
ARCHIVE_NAMES = ("Archive", "Archiv", "Archives", "Archivio")
# folders a message never goes to: the mail program's own ones (tidy.Box.is_special plus the names without flags)
NEVER = re.compile(r"(?i)^(trash|papierkorb|gelöscht\w*|deleted( items| messages)?|junk|spam|"
                   r"sent( items| messages)?|gesendet\w*|drafts?|entwürfe)$")
_lock = threading.Lock()
_trees = {}   # uid -> (time, tree): the folder tree of the page, memory only
_today = {"day": "", "n": 0}   # Live: how many messages were ordered on the page today (a number, never which)


def _account(uid, ref):
    """(account, uid in the inbox) of an id "<account>:<uid>" of an own mailbox, else ValueError."""
    m = re.fullmatch(r"(m[0-9a-f]{8}):(\d{1,10})", str(ref or "").strip())
    acct = next((a for a in mail.get(uid)["accounts"] if m and a["id"] == m.group(1)), None)
    if not acct:
        raise ValueError("unknown message id")
    return acct, int(m.group(2))


def _targets(box):
    """{name shown: server name} of the folders a message may go to, and the archive folder's name (or None)."""
    out = {}
    for n, x in box.boxes.items():
        last = n.split(box.delim)[-1]
        if n.upper() == "INBOX" or "\\noselect" in x["flags"] or NEVER.match(last):
            continue
        if re.search(r"\\(sent|drafts|trash|junk|all|flagged|important)", x["flags"]):
            continue
        out[n] = n
    arch = next((n for n, x in box.boxes.items() if "\\archive" in x["flags"]), None) \
        or next((n for n in box.boxes if n.split(box.delim)[-1] in ARCHIVE_NAMES), None)
    return dict(sorted(out.items(), key=lambda kv: kv[0].lower())), arch


def folders(uid, account_id):
    """The folders of one own mailbox the page may move to (names only) and which one is the archive."""
    acct = next((a for a in mail.get(uid)["accounts"] if a["id"] == account_id), None)
    if not acct:
        raise ValueError("unknown mailbox")
    with tidy.Box(acct) as box:
        t, arch = _targets(box)
    return {"folders": list(t)[:100], "archive": arch}


def _mid(box, u):
    h = box.headers([u], "MESSAGE-ID").get(u)
    return str(h.get("Message-ID") or "").strip()[:300] if h is not None else ""


def act(uid, ref, action, folder="", mid="", src="INBOX"):
    """One action on one message of the inbox or of the folder `src`; {"done": action, "mid": its Message-ID,
    "folder": where it went}. ValueError for anything not allowed, LookupError when the message is no longer there."""
    inbox = str(src or "INBOX").upper() == "INBOX"
    # the cached inbox listing follows a change of one of its messages; anything coming into the inbox drops it
    return _outcome(uid, action, lambda: _act(uid, ref, action, folder, mid, src),
                   ref if inbox or (action in ("move", "back") and folder.upper() == "INBOX") else "", inbox=inbox)


def act_many(uid, refs, action, folder="", src="INBOX"):
    """Mehrfachauswahl: one action on up to MANY messages of one folder (read, unread, flag, unflag, archive, move);
    {"done": action, "n": how many, "moved": [{"acct", "mids"}], "folder"}. A move goes into one mailbox's folder,
    so all messages have to be of that mailbox."""
    return _outcome(uid, action, lambda: _act_many(uid, refs, action, folder, src), "", len(refs))


def _outcome(uid, action, fn, ref, n=1, inbox=True):
    who = profiles.log_name(profiles.by_id(uid))
    many = " many" if n > 1 else ""
    try:
        out = fn()
    except notaus.NotausAktiv:
        print(f"mail: page{many} {action} refused, notaus | {who}", flush=True)
        raise
    except LookupError:
        print(f"mail: page{many} {action} refused, not found | {who}", flush=True)
        raise
    except Exception as e:
        print(f"mail: page{many} {action} failed ({type(e).__name__}) | {who}", flush=True)
        raise
    print(f"mail: page{many} {action} done | {n} | {who}", flush=True)
    with _lock:
        day = time.strftime("%Y-%m-%d")
        if _today["day"] != day:
            _today.update(day=day, n=0)
        _today["n"] += n
    if n == 1:
        mail.changed(uid, ref if inbox else "", action)   # the cached listing follows at once, no new fetch
    if n > 1 or action in ("archive", "move", "back"):
        _trees.pop(uid, None)
    return out


def today():
    return _today["n"] if _today["day"] == time.strftime("%Y-%m-%d") else 0


def role(box, name):
    """What a folder is for the page: inbox, sent, drafts, trash, junk, archive, all (Gmail's views), group (holds
    folders only) or folder (an ordinary one)."""
    x = box.boxes.get(name) or {"flags": ""}
    last = name.split(box.delim)[-1].strip().lower()
    if name.upper() == "INBOX":
        return "inbox"
    for flag, r in (("\\sent", "sent"), ("\\drafts", "drafts"), ("\\trash", "trash"), ("\\junk", "junk"),
                    ("\\archive", "archive"), ("\\all", "all"), ("\\flagged", "all"), ("\\important", "all")):
        if flag in x["flags"]:
            return r
    if "\\noselect" in x["flags"]:
        return "group"
    if re.match(r"(?i)^(sent( items| messages| mail)?|gesendet\w*|gesendete \w+)$", last):
        return "sent"
    if re.match(r"(?i)^(drafts?|entwürfe)$", last):
        return "drafts"
    if re.match(r"(?i)^(trash|papierkorb|gelöscht\w*|deleted( items| messages)?|gelöschte \w+)$", last):
        return "trash"
    if re.match(r"(?i)^(junk|spam|junk-e-mail)$", last):
        return "junk"
    if name.split(box.delim)[-1] in ARCHIVE_NAMES:
        return "archive"
    if tidy.reserved(last):
        return "all"
    return "folder"


def _tidy_owned(uid, box):
    """The folders „Mails aufräumen“ keeps (its main folder and what is inside): renamed there, never here."""
    d = tidy.state(uid)
    now, ever = tidy.our_folders(d)
    out = {box.name(p) for p in ever}
    root = box.name(d["root"]) if d.get("root") else ""
    return out, root


def _own(uid, box, name):
    """An own folder the page may rename or remove: an ordinary folder, not one of „Mails aufräumen“."""
    if name not in box.boxes or role(box, name) != "folder" or box.is_special(name):
        return False
    owned, root = _tidy_owned(uid, box)
    return name not in owned and not (root and (name == root or name.startswith(root + box.delim)))


ORDER = {"inbox": 0, "drafts": 1, "sent": 2, "archive": 3, "folder": 4, "group": 4, "all": 5, "junk": 6, "trash": 7}


def tree(uid, fresh=False):
    """The page E-Mail (Ordner): per mailbox its folders with what they are for, how many unread and whether the
    profile may rename or remove them; kept TREE_SECONDS. Folder names come from the mail server: data for esc()."""
    hit = _trees.get(uid)
    if hit and not fresh and time.time() - hit[0] < TREE_SECONDS:
        return hit[1]
    out = []
    for acct in mail.get(uid)["accounts"]:
        row = {"id": acct["id"], "name": acct.get("name", ""), "delim": "/", "folders": [], "error": False}
        try:
            with tidy.Box(acct) as box:
                row["delim"] = box.delim
                names = sorted(box.boxes, key=lambda n: (ORDER[role(box, n)], n.lower()))[:TREE_MAX]
                for n in names:
                    r = role(box, n)
                    unseen = None
                    if r != "group" and r not in ("trash", "junk", "all"):
                        unseen = _unseen(box, n)
                    row["folders"].append({"name": n, "role": r, "depth": n.count(box.delim) if box.delim else 0,
                                           "unseen": unseen, "own": _own(uid, box, n),
                                           "into": r in ("inbox", "folder", "archive")})
        except (OSError, ValueError, imaplib.IMAP4.error):
            row["error"] = True
        out.append(row)
    res = {"accounts": out}
    _trees[uid] = (time.time(), res)
    return res


def _unseen(box, name):
    raw = box.boxes.get(name, {}).get("raw") or tidy._utf7(name)
    try:
        typ, data = box.c.status(tidy._q(raw), "(UNSEEN)")
    except imaplib.IMAP4.error:
        return None
    m = re.search(rb"UNSEEN (\d+)", b" ".join(x for x in (data or []) if isinstance(x, bytes)))
    return int(m.group(1)) if typ == "OK" and m else None


def _acct(uid, account_id):
    acct = next((a for a in mail.get(uid)["accounts"] if a["id"] == account_id), None)
    if not acct:
        raise ValueError("unknown mailbox")
    return acct


def listing(uid, account_id, folder, query=""):
    """The newest LIST_MAX messages of one folder (EXAMINE: nothing changes), header fields only, like mail.inbox;
    with a search (mail._words: von:, betreff:, hat:anhang …) those of the newest mail.HEADER_SCAN that fit."""
    acct = _acct(uid, account_id)
    words = mail._words(str(query)[:100])
    with tidy.Box(acct) as box:
        if folder not in box.boxes or role(box, folder) == "group":
            raise LookupError("no such folder")
        box.select(folder)
        uids = sorted(box.search("ALL"))[-(mail.HEADER_SCAN if words else LIST_MAX):]
        heads = mail.head_rows(box.c, uids)
    hits = [(u, h) for u, h in heads.items() if mail.fits(words, h)]
    items = sorted(({"id": f"{acct['id']}:{u}", "from": mail.known(uid, h["from"]), "subject": h["subject"] or "",
                     "date": int(h["date"].timestamp()), "unread": bool(h["unread"]), "flagged": bool(h["flagged"]),
                     "attach": bool(h["attach"]), "box": 0} for u, h in hits), key=lambda x: x["date"], reverse=True)[:LIST_MAX]
    return {"connected": True, "boxes": [acct.get("name", "")], "errors": [], "items": items, "folder": folder,
            "account": acct["id"]}


def _source(box, src, moving):
    """The folder a message is changed in: the inbox or a folder of the mailbox; moved only out of the inbox, an
    ordinary folder or the archive (never out of sent, drafts, trash or junk)."""
    if src.upper() == "INBOX":
        return "INBOX"
    if src not in box.boxes or role(box, src) == "group":
        raise LookupError("no such folder")
    if moving and role(box, src) not in ("folder", "archive"):
        raise ValueError("messages are moved only out of the inbox, an own folder or the archive")
    return src


def _store(box, uids, action):
    flag = "(\\Seen)" if action in ("read", "unread") else "(\\Flagged)"
    sign = "+" if action in ("read", "flag") else "-"
    typ, _ = box.c.uid("STORE", ",".join(map(str, uids)), sign + "FLAGS.SILENT", flag)
    if typ != "OK":
        raise ValueError(f"the mail server refused ({typ})")


def _dest(box, targets, arch, action, folder, src):
    dst = arch if action == "archive" else folder
    if not dst:
        raise ValueError("this mailbox has no archive folder")
    if dst != "INBOX" and dst not in targets:
        raise ValueError("not a folder a message may go to")
    if dst == src:
        raise ValueError("the message is in this folder already")
    return dst


def _act(uid, ref, action, folder, mid, src="INBOX"):
    if action not in ACTIONS:
        raise ValueError("unknown action")
    notaus.stop("aktion", uid)   # the Notaus (or the profile's own) holds every action off (notaus.py)
    acct, u = _account(uid, ref)
    with tidy.Box(acct) as box:
        targets, arch = _targets(box)
        if action == "back":
            # right after archive or move: the same message (its Message-ID) from that folder back where it was
            home = _source(box, src or "INBOX", True)
            if folder not in targets or not mid:
                raise ValueError("only back from an own folder, with the message's id")
            box.select(folder, write=True)
            hits = box.find_mid(mid)
            if len(hits) != 1:
                raise LookupError("the message is not there")
            _move(box, hits, home)
            return {"done": action, "mid": mid, "folder": home}
        moving = action in ("archive", "move")
        here = _source(box, src or "INBOX", moving)
        box.select(here, write=True)
        if not box.headers([u], "MESSAGE-ID"):
            raise LookupError("the message is not there")
        if not moving:
            _store(box, [u], action)
            return {"done": action, "mid": "", "folder": ""}
        dst = _dest(box, targets, arch, action, folder, here)
        m = _mid(box, u)
        _move(box, [u], dst)
        return {"done": action, "mid": m, "folder": dst}


def _act_many(uid, refs, action, folder, src="INBOX"):
    if action not in ACTIONS or action == "back":
        raise ValueError("unknown action")
    refs = list(dict.fromkeys(str(r) for r in refs))
    if not refs or len(refs) > MANY:
        raise ValueError(f"one to {MANY} messages at a time")
    notaus.stop("aktion", uid)
    groups = {}
    for r in refs:
        acct, u = _account(uid, r)
        groups.setdefault(acct["id"], (acct, []))[1].append(u)
    moving = action in ("archive", "move")
    if action == "move" and len(groups) > 1:
        raise ValueError("a move goes into the folder of one mailbox: pick messages of one mailbox")
    n, moved, where = 0, [], ""
    for acct, uids in groups.values():
        with tidy.Box(acct) as box:
            targets, arch = _targets(box)
            here = _source(box, src or "INBOX", moving)
            box.select(here, write=True)
            there = [u for u in uids if u in box.headers(uids, "MESSAGE-ID")]
            if not there:
                continue
            if not moving:
                _store(box, there, action)
            else:
                dst = _dest(box, targets, arch, action, folder, here)
                mids = [str(h.get("Message-ID") or "").strip()[:300] for h in box.headers(there, "MESSAGE-ID").values()]
                _move(box, there, dst)
                moved.append({"acct": acct["id"], "mids": [m for m in mids if m][:MANY]})
                where = dst
            n += len(there)
    if not n:
        raise LookupError("the messages are not there")
    for r in refs:
        mail.changed(uid, r if (src or "INBOX").upper() == "INBOX" else "", action)
    return {"done": action, "n": n, "moved": moved, "folder": where}


def back_many(uid, account_id, folder, mids, src="INBOX"):
    """„Rückgängig“ after a Mehrfachauswahl: the messages (their Message-IDs) from `folder` back to `src`."""
    return _outcome(uid, "back", lambda: _back_many(uid, account_id, folder, mids, src), "", max(2, len(mids)))


def _back_many(uid, account_id, folder, mids, src):
    notaus.stop("aktion", uid)
    acct = _acct(uid, account_id)
    ids = [tidy.clean_mid(m) for m in mids][:MANY]
    if not any(ids):
        raise ValueError("only with the messages' ids")
    with tidy.Box(acct) as box:
        targets, _ = _targets(box)
        home = _source(box, src or "INBOX", True)
        if folder not in targets:
            raise ValueError("only back from an own folder")
        box.select(folder, write=True)
        hits = [h for m in ids if m for h in box.find_mid(m)[:1]]
        if not hits:
            raise LookupError("the messages are not there")
        _move(box, hits, home)
    return {"done": "back", "n": len(hits), "folder": home}


# ---------------------------------------------------------------- folders
def _clean(box, name):
    """A new folder's name: no separator, no control or wildcard characters, not a mail program's folder."""
    v = tidy.clean_name(str(name or "").replace(box.delim, " "))
    if not v or tidy.reserved(v) or NEVER.match(v) or v in ARCHIVE_NAMES:
        raise ValueError("pick another name (not empty, not a folder of the mail program)")
    return v


def folder_op(uid, account_id, op, folder="", name=""):
    """Ordner: "new" (name, inside `folder` or at the top when it is empty), "rename" (an own folder, same place) or
    "remove" (an own folder that is empty and holds no folders). {"done": op, "folder": the new path}."""
    who = profiles.log_name(profiles.by_id(uid))
    try:
        out = _folder_op(uid, account_id, op, folder, name)
    except notaus.NotausAktiv:
        print(f"mail: folder {op} refused, notaus | {who}", flush=True)
        raise
    except LookupError:
        print(f"mail: folder {op} refused, not found | {who}", flush=True)
        raise
    except ValueError:
        print(f"mail: folder {op} refused | {who}", flush=True)
        raise
    except Exception as e:
        print(f"mail: folder {op} failed ({type(e).__name__}) | {who}", flush=True)
        raise
    print(f"mail: folder {op} done | {who}", flush=True)
    with _lock:
        day = time.strftime("%Y-%m-%d")
        if _today["day"] != day:
            _today.update(day=day, n=0)
        _today["n"] += 1   # Live: a number, never which folder
    _trees.pop(uid, None)
    return out


def _folder_op(uid, account_id, op, folder, name):
    if op not in ("new", "rename", "remove"):
        raise ValueError("unknown folder action")
    notaus.stop("aktion", uid)
    acct = _acct(uid, account_id)
    with tidy.Box(acct) as box:
        if op == "new":
            if folder and (folder not in box.boxes or role(box, folder) not in ("folder", "group", "inbox")):
                raise ValueError("a new folder goes at the top or inside an own folder")
            path = (folder + box.delim if folder else "") + _clean(box, name)
            if path in box.boxes:
                raise ValueError("this folder exists already")
            if len(box.boxes) >= 500:
                raise ValueError("this mailbox has enough folders")
            typ, _ = box.c.create(tidy._q(tidy._utf7(path)))
            if typ != "OK":
                raise ValueError(f"the mail server refused the new folder ({typ})")
            try:
                box.c.subscribe(tidy._q(tidy._utf7(path)))
            except Exception:
                pass
            return {"done": op, "folder": path}
        if folder not in box.boxes:
            raise LookupError("no such folder")
        if not _own(uid, box, folder):
            raise ValueError("only own folders are renamed or removed (not the mail program's, not those of Mails aufräumen)")
        raw = box.boxes[folder]["raw"]
        if op == "rename":
            parent = folder.rsplit(box.delim, 1)[0] + box.delim if box.delim in folder else ""
            path = parent + _clean(box, name)
            if path in box.boxes:
                raise ValueError("a folder with this name exists already")
            typ, _ = box.c.rename(tidy._q(raw), tidy._q(tidy._utf7(path)))
            if typ != "OK":
                raise ValueError(f"the mail server refused to rename ({typ})")
            try:
                box.c.subscribe(tidy._q(tidy._utf7(path)))
            except Exception:
                pass
            return {"done": op, "folder": path}
        # remove: only an empty folder without folders inside; the messages of a folder are never deleted
        if any(n.startswith(folder + box.delim) for n in box.boxes):
            raise ValueError("the folder holds folders: empty it first")
        typ, data = box.c.status(tidy._q(raw), "(MESSAGES)")
        m = re.search(rb"MESSAGES (\d+)", b" ".join(x for x in (data or []) if isinstance(x, bytes)))
        if typ != "OK" or not m or int(m.group(1)) != 0:
            raise ValueError("only an empty folder is removed: move its messages first")
        try:
            box.c.unsubscribe(tidy._q(raw))
        except Exception:
            pass
        typ, _ = box.c.delete(tidy._q(raw))
        if typ != "OK":
            raise ValueError(f"the mail server refused to remove the folder ({typ})")
        return {"done": op, "folder": ""}


def _move(box, uids, dst):
    if not box.can_move():
        raise ValueError("the mail server cannot move messages (neither IMAP MOVE nor UIDPLUS)")
    raw = box.boxes.get(dst, {}).get("raw") or tidy._utf7(dst)
    if "MOVE" in box.caps:
        typ, _ = box.c.uid("MOVE", ",".join(map(str, uids)), tidy._q(raw))
        if typ != "OK":
            raise ValueError(f"the mail server refused the move ({typ})")
    elif not box._copy_then_remove(uids, raw, dst):
        raise ValueError("the mail server did not confirm the copy")
