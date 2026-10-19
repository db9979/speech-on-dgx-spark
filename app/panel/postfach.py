"""Mails ordnen auf der Seite E-Mail (plan kalender-mail Stufe 2, function "Mails ordnen", chat.mail_manage, off):
the profile marks a message of its inbox as read or unread, archives it or moves it into one of its own folders,
and takes that back right after. Writing to the mailbox knows exactly these four things:

  - the flag \\Seen on one message of the inbox (UID STORE)
  - one message from the inbox into the archive folder (the server's \\Archive folder, else "Archive"/"Archiv")
    or into an ordinary folder of the mailbox
  - the same message back from there into the inbox (found again by its Message-ID)
  - nothing else: never into the trash, the junk, the sent or the drafts folder, never deleted, never a folder
    created or renamed (tidy.py creates its own folders)

A button on the page is the person's own yes. The connection is tidy.Box (netguard.USER, TLS only); MOVE, or COPY
and then UID EXPUNGE of exactly the confirmed original where MOVE is missing (iCloud). Logs carry fixed words and
the profile's log name only, never a sender, a subject or a folder.
"""
import re
import threading
import time

import mail
import notaus
import profiles
import tidy

ACTIONS = ("read", "unread", "archive", "move", "back")
ARCHIVE_NAMES = ("Archive", "Archiv", "Archives", "Archivio")
# folders a message never goes to: the mail program's own ones (tidy.Box.is_special plus the names without flags)
NEVER = re.compile(r"(?i)^(trash|papierkorb|gelöscht\w*|deleted( items| messages)?|junk|spam|"
                   r"sent( items| messages)?|gesendet\w*|drafts?|entwürfe)$")
_lock = threading.Lock()
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


def act(uid, ref, action, folder="", mid=""):
    """One action on one message; {"done": action, "mid": its Message-ID, "folder": where it went}. ValueError for
    anything not allowed, LookupError when the message is no longer there."""
    who = profiles.log_name(profiles.by_id(uid))
    try:
        out = _act(uid, ref, action, folder, mid)
    except notaus.NotausAktiv:
        print(f"mail: page {action} refused, notaus | {who}", flush=True)
        raise
    except LookupError:
        print(f"mail: page {action} refused, not found | {who}", flush=True)
        raise
    except Exception as e:
        print(f"mail: page {action} failed ({type(e).__name__}) | {who}", flush=True)
        raise
    print(f"mail: page {action} done | {who}", flush=True)
    with _lock:
        day = time.strftime("%Y-%m-%d")
        if _today["day"] != day:
            _today.update(day=day, n=0)
        _today["n"] += 1
    mail.changed(uid, ref, action)   # the cached listing follows at once, no new fetch
    return out


def today():
    return _today["n"] if _today["day"] == time.strftime("%Y-%m-%d") else 0


def _act(uid, ref, action, folder, mid):
    if action not in ACTIONS:
        raise ValueError("unknown action")
    notaus.stop("aktion", uid)   # the Notaus (or the profile's own) holds every action off (notaus.py)
    acct, u = _account(uid, ref)
    with tidy.Box(acct) as box:
        targets, arch = _targets(box)
        if action == "back":
            # right after archive or move: the same message (its Message-ID) from that folder into the inbox
            if folder not in targets or not mid:
                raise ValueError("only back from an own folder, with the message's id")
            box.select(folder, write=True)
            hits = box.find_mid(mid)
            if len(hits) != 1:
                raise LookupError("the message is not there")
            _move(box, hits, "INBOX")
            return {"done": action, "mid": mid, "folder": "INBOX"}
        box.select("INBOX", write=True)
        if not box.headers([u], "MESSAGE-ID"):
            raise LookupError("the message is not there")
        if action in ("read", "unread"):
            typ, _ = box.c.uid("STORE", str(u), ("+" if action == "read" else "-") + "FLAGS.SILENT", "(\\Seen)")
            if typ != "OK":
                raise ValueError(f"the mail server refused ({typ})")
            return {"done": action, "mid": "", "folder": ""}
        dst = arch if action == "archive" else folder
        if not dst:
            raise ValueError("this mailbox has no archive folder")
        if dst not in targets:
            raise ValueError("not a folder a message may go to")
        m = _mid(box, u)
        _move(box, [u], dst)
        return {"done": action, "mid": m, "folder": dst}


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
