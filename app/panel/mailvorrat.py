"""Mail-Vorrat (Dominik 2026-10-20 „ja, so umsetzen“, part of E-Mail lesen with no switch of its own: „es sollte eine
Standardfunktionalität sein“): the newest of each profile's mailboxes kept on the Spark, so the page, the assistant,
the deadlines and „Für dich“ answer at once after a restart and answer from it, with its time, when a mailbox does
not answer instead of saying „nicht erreichbar“.

    USERS_DIR/<user id>/mail-vorrat.bin   sealed with AES-GCM (vorrat.Vorrat, the one way for such a supply)

- Per mailbox at most HEADS headers (sender, subject, time, read and flag marks) of the last DAYS days, the newest;
  per profile at most TEXTS message texts (the newest fetched ahead and the ones opened), each at most TEXT_MAX
  characters of plain text. Never an attachment, never HTML, never a picture.
- Only what mail.py read anyway (EXAMINE, PEEK): this module never opens a mailbox itself.
- Gone with the mailbox (mail.remove), with all mailboxes (mail.forget), with the profile (its folder) and after
  IDLE_DAYS without anybody reading the mail (sweep(): the file is written only while the profile reads).
- Written at most every WRITE_EVERY seconds per profile, never in plain text, without cryptography not at all.
- Live (node E-Mail): profiles with a supply and answers from it today, numbers only.
"""
import datetime
import email.message
import email.policy
import re
import time

from common import DayCounter
from vorrat import Vorrat

NAME = "mail-vorrat.bin"
HEADS = 300           # headers kept per mailbox (the newest)
DAYS = 30             # headers older than this go
TEXTS = 40            # message texts kept per profile (the newest used)
TEXT_MAX = 4000       # characters of one text (mail.MAX_TEXT)
WRITE_EVERY = 300     # seconds: a profile's file is written at most this often; flush() writes the rest
IDLE_DAYS = 14        # a supply nobody read for this long is deleted (sweep)

_v = Vorrat(NAME, IDLE_DAYS, WRITE_EVERY, empty=lambda: {"heads": {}, "texts": {}, "at": {}})
_lock = _v.lock
_used = DayCounter(antworten=0)   # Live: answers from the supply today (a number, never what)


def _file(uid):
    return _v.file(uid)


def _load(uid):
    return _v.load(uid)


def _save(uid, now=None, force=False):
    _v.changed(uid, now, force)


def flush(now=None):
    """Writes every changed supply (mail.keep_fresh_loop, every few minutes). Returns how many."""
    try:
        return _v.flush(now)
    except OSError:
        print("mail: supply not written", flush=True)
        return 0


def _head_out(h):
    return {"from": str(h.get("from", ""))[:300], "subject": str(h.get("subject", ""))[:300],
            "date": int(h["date"].timestamp()), "unread": bool(h.get("unread")), "flagged": bool(h.get("flagged")),
            "attach": bool(h.get("attach"))}


def _head_in(h):
    return dict(h, date=datetime.datetime.fromtimestamp(int(h.get("date", 0)), datetime.timezone.utc))


def keep_heads(uid, found, aids, now=None):
    """A listing of the inboxes without words was read (mail._start): its headers into the supply of the mailboxes
    that answered (aids), the newest HEADS of the last DAYS days each."""
    now = time.time() if now is None else now
    d = _load(uid)
    cut = now - DAYS * 86400
    with _lock:
        for aid in aids:
            box = d["heads"].setdefault(aid, {})
            for a, u, h in found:
                if a == aid:
                    box[str(u)] = _head_out(h)
            keep = sorted(((h["date"], u) for u, h in box.items() if h["date"] >= cut), reverse=True)[:HEADS]
            d["heads"][aid] = {u: box[u] for _, u in keep}
            d["at"][aid] = int(now)
    _save(uid, now)


def heads(uid, aid, fits, days, unread, limit, now=None):
    """[(aid, uid, header)] of one mailbox from the supply, newest first, and when it was read; ([], 0) without.
    fits(header) decides the words (mail.fits)."""
    now = time.time() if now is None else now
    d = _load(uid)
    box, at = d["heads"].get(aid), d["at"].get(aid, 0)
    if not box:
        return [], 0
    since = now - days * 86400
    got = [(aid, int(u), _head_in(h)) for u, h in box.items()
           if h["date"] >= since and (h.get("unread") or not unread) and fits(_head_in(h))]
    got.sort(key=lambda x: x[2]["date"], reverse=True)
    return got[:limit], at


def has(uid, aid):
    return bool(_load(uid)["heads"].get(aid))


def keep_text(uid, ref, msg, text, now=None):
    """An inbox message was read (mail._keep_body): its plain text (mail.plain) into the supply, the newest TEXTS."""
    now = time.time() if now is None else now
    d = _load(uid)
    with _lock:
        d["texts"][str(ref)] = {"from": str(msg.get("From", ""))[:300], "to": str(msg.get("To", ""))[:300],
                                "date": str(msg.get("Date", ""))[:100], "subject": str(msg.get("Subject", ""))[:300],
                                "mid": re.sub(r"[\s\x00-\x1f]", "", str(msg.get("Message-ID", "")))[:300],
                                "text": str(text or "")[:TEXT_MAX], "t": int(now)}
        keep = sorted(d["texts"].items(), key=lambda kv: kv[1].get("t", 0), reverse=True)[:TEXTS]
        d["texts"] = dict(keep)
    _save(uid, now)


def text(uid, ref):
    """The kept message as a small plain-text message (no attachments), or None."""
    x = _load(uid)["texts"].get(str(ref))
    if not x:
        return None
    msg = email.message.EmailMessage(policy=email.policy.default)
    for k, name in (("from", "From"), ("to", "To"), ("date", "Date"), ("subject", "Subject"), ("mid", "Message-ID")):
        v = re.sub(r"[\r\n]+", " ", x.get(k, ""))
        if v:
            try:
                msg[name] = v
            except (ValueError, TypeError):
                pass
    msg.set_content(x.get("text", "") or "")
    return msg


def used():
    """mail.py answered from the supply (a listing or a message): counted for Live."""
    _used.bump("antworten")


def changed(uid, aid, u, action):
    """The page changed one inbox message (mail.changed): its marks follow, archived, moved or deleted it goes."""
    d = _load(uid)
    with _lock:
        box = d["heads"].get(aid) or {}
        h = box.get(str(u))
        if h is None:
            return
        if action in ("archive", "move", "delete", "erase"):
            box.pop(str(u), None)
            d["texts"].pop(f"{aid}:{u}", None)
        elif action in ("read", "unread"):
            h["unread"] = action == "unread"
        elif action in ("flag", "unflag"):
            h["flagged"] = action == "flag"
    _save(uid)


def drop(uid, aid):
    """One mailbox removed: its headers and texts go."""
    d = _load(uid)
    with _lock:
        d["heads"].pop(aid, None)
        d["at"].pop(aid, None)
        d["texts"] = {k: v for k, v in d["texts"].items() if not k.startswith(aid + ":")}
    _save(uid, force=True)


def forget(uid):
    """All mailboxes removed (mail.forget): the supply goes, file and memory."""
    _v.forget(uid)


def sweep(now=None):
    """Supplies nobody read for IDLE_DAYS go (the file is written only while its profile reads). Returns how many."""
    n = _v.sweep(now)
    if n:
        print(f"mail: supply swept | {n} profiles", flush=True)
    return n


def for_live():
    """Live (node E-Mail): profiles with a supply in memory and answers from it today; numbers only."""
    return {"profiles": sum(1 for d in _v.mem.values() if d["heads"]), "answers": _used.counts()["antworten"]}
