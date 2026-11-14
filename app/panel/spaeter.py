"""Zurückstellen (pl_mail-Ideen 2, Dominik 2026-11-13 „1-7“ and „ok“ to plan pl-mail/plan.md, an idea seen in pl_mail,
own code): a mail goes out of the inbox into the folder „<KI folder>/Später“ of its own mailbox and comes back into the
inbox at the time picked, unread, so it stands on top again.

- Off until the admin switches chat.mail_later on (Funktionen → E-Mail lesen → Mails ordnen → „Zurückstellen“); it
  builds on „Mails ordnen“ (it moves mails). Then for every profile that may order mail (the admin can block single
  profiles), never for guests, never a tool of the model: the page E-Mail, the iPhone app and Android (panel view) only.
- Fixed times (WHEN): heute Abend 18 Uhr, morgen früh 8 Uhr, am Wochenende Samstag 9 Uhr, nächste Woche Montag 8 Uhr,
  or a date and time from MIN_AHEAD to MAX_DAYS ahead. Times are the profile's (chat.user_zone).
- The list (Message-ID, mailbox, time, sender and subject for the list of „Später“) stays sealed in the profile's
  folder (mail-zurueck.bin, at most MAX entries); the mail itself stays on the mail server.
- due() every minute (panel.every_minute): what is due goes back into the inbox and loses \\Seen. That also runs when
  the switch was turned off later, so no mail stays away. A mail the person moved away themselves is dropped from the
  list; a mailbox that does not answer is tried again the next minute (a log line at most every FAIL_LOG seconds).
- „Jetzt zurückholen“ brings one back at once. The Notaus (or the profile's own) holds both off (notaus.stop).
- Logs carry fixed words and numbers, the profile only as profiles.log_name; Live (node E-Mail) shows how many wait and
  how many came back today.
"""
import asyncio
import datetime
import re
import threading
import time

import features
import mail
import notaus
import postfach
import profiles
import tidy
from chat import user_zone
from common import DayCounter
from vorrat import Vorrat

FOLDER = "Später"            # under the KI folder of „Postfach aufräumen“ (tidy state root, "Spark" unless renamed)
MAX = 200                    # mails waiting per profile
MIN_AHEAD = 5 * 60           # a picked time at least this far ahead
MAX_DAYS = 365
FAIL_LOG = 1800
WHEN = ("abend", "morgen", "wochenende", "woche")
STORE = Vorrat("mail-zurueck.bin", idle_days=MAX_DAYS + 35, write_every=0)
_count = DayCounter(gelegt=0, zurueck=0)
_failed = {}                 # uid -> time of the last „not reached“ line
_lock = threading.Lock()


def path(uid):
    """„<KI folder>/Später“ in our "/" spelling; the name is fixed, never from a mail."""
    st = tidy.state(uid)
    return f"{st['root']}/{FOLDER}" if st.get("root") else FOLDER


def when(choice, now):
    """The time (an aware datetime in the profile's zone) of a fixed choice, from now (an aware datetime)."""
    day = now.replace(second=0, microsecond=0)
    if choice == "abend":
        t = day.replace(hour=18, minute=0)
        return t if t - now >= datetime.timedelta(seconds=MIN_AHEAD) else t + datetime.timedelta(days=1)
    if choice == "morgen":
        return (day + datetime.timedelta(days=1)).replace(hour=8, minute=0)
    if choice == "wochenende":
        t = (day + datetime.timedelta(days=(5 - day.weekday()) % 7)).replace(hour=9, minute=0)
        return t if t - now >= datetime.timedelta(seconds=MIN_AHEAD) else t + datetime.timedelta(days=7)
    if choice == "woche":
        return (day + datetime.timedelta(days=7 - day.weekday())).replace(hour=8, minute=0)
    raise ValueError("unknown time")


def until(uid, choice, at=0, now=None):
    """Epoch seconds the mail comes back: a fixed choice, or at (epoch seconds) between MIN_AHEAD and MAX_DAYS ahead."""
    now = time.time() if now is None else now
    if choice == "at":
        if not isinstance(at, (int, float)) or not (now + MIN_AHEAD <= at <= now + MAX_DAYS * 86400):
            raise ValueError("pick a time from five minutes to a year ahead")
        return int(at)
    zone = user_zone(profiles.by_id(uid))
    return int(when(choice, datetime.datetime.fromtimestamp(now, zone)).timestamp())


def items(uid):
    d = STORE.load(uid)
    return [x for x in d.get("v") or [] if isinstance(x, dict) and x.get("mid") and x.get("acct")]


def _save(uid, v):
    STORE.load(uid)["v"] = v[-MAX:]
    STORE.changed(uid, force=True)


def liste(uid):
    """„Später“: what waits, the soonest first: [{mid, acct, until, from, subject}]."""
    return sorted(({k: x.get(k) for k in ("mid", "acct", "until", "from", "subject")} for x in items(uid)),
                  key=lambda x: x["until"])


def put(uid, ref, at_until, src="INBOX"):
    """Zurückstellen: the mail ref ("<account>:<uid>") of the inbox into „Später“ until at_until (epoch seconds)."""
    notaus.stop("aktion", uid)
    if (src or "INBOX").upper() != "INBOX":
        raise ValueError("only mails of the inbox are put off")
    have = items(uid)
    if len(have) >= MAX:
        raise ValueError(f"at most {MAX} mails wait at once")
    acct, u = postfach._account(uid, ref)
    with tidy.Box(acct) as box:
        if not box.can_move():
            raise ValueError("the mail server cannot move messages (neither IMAP MOVE nor UIDPLUS)")
        dst = box.own(path(uid))
        box.select("INBOX", write=True)
        h = box.headers([u], "MESSAGE-ID FROM SUBJECT").get(u)
        if h is None:
            raise LookupError("the message is not there")
        mid = tidy.clean_mid(h.get("Message-ID"))
        if not mid:
            raise ValueError("a mail without Message-ID cannot be found again")
        postfach._move(box, [u], dst)
    entry = {"mid": mid, "acct": acct["id"], "until": int(at_until), "t": int(time.time()),
             "from": mail._hdr(h.get("From", ""))[:80], "subject": mail._hdr(h.get("Subject", ""))[:120]}
    with _lock:
        _save(uid, [x for x in items(uid) if x["mid"] != mid] + [entry])
    mail.changed(uid, ref, "move")
    _count.bump("gelegt")
    print(f"mail: later put | {_hours(at_until)} h | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return {"done": "later", "mid": mid, "until": int(at_until)}


def _hours(t):
    return max(0, round((t - time.time()) / 3600))


def _back(uid, acct, mids):
    """Moves the mails (Message-IDs) of one mailbox from „Später“ into the inbox, unread. Returns (back, gone)."""
    back, gone = [], []
    with tidy.Box(acct) as box:
        name = box.name(path(uid))
        if name not in box.boxes:
            return [], list(mids)
        box.select(name, write=True)
        found = {}
        for m in mids:
            hits = box.find_mid(m)
            if hits:
                found[m] = hits[0]
            else:
                gone.append(m)
        if found:
            postfach._move(box, list(found.values()), "INBOX")
            box.select("INBOX", write=True)
            for m in found:
                for u in box.find_mid(m)[:1]:
                    box.c.uid("STORE", str(u), "-FLAGS", "(\\Seen)")
                back.append(m)
    return back, gone


def bring(uid, pick=None, now=None):
    """Brings back what is due (or the Message-IDs in pick at once). Returns how many came back."""
    now = time.time() if now is None else now
    have = items(uid)
    due = [x for x in have if (x["mid"] in pick if pick is not None else x["until"] <= now)]
    if not due:
        return 0
    who = profiles.log_name(profiles.by_id(uid))
    accts = {a["id"]: a for a in mail.get(uid)["accounts"]}
    done, n = set(), 0
    for aid in dict.fromkeys(x["acct"] for x in due):
        mids = [x["mid"] for x in due if x["acct"] == aid]
        if aid not in accts:                     # the mailbox was removed: nothing to bring back
            done.update(mids)
            print(f"mail: later dropped, mailbox gone | {len(mids)} | {who}", flush=True)
            continue
        try:
            back, gone = _back(uid, accts[aid], mids)
        except Exception as e:
            if now - _failed.get(uid, 0) >= FAIL_LOG:
                _failed[uid] = now
                print(f"mail: later not reached ({type(e).__name__}) | {len(mids)} | {who}", flush=True)
            continue
        done.update(back + gone)
        n += len(back)
        if gone:
            print(f"mail: later gone | {len(gone)} | {who}", flush=True)
    if done:
        with _lock:
            _save(uid, [x for x in items(uid) if x["mid"] not in done])
        mail.changed(uid, "", "back")      # the inbox listings are read anew
    if n:
        _count.bump("zurueck", n)
        print(f"mail: later back | {n} | {who}", flush=True)
    return n


def back_now(uid, mid):
    """„Jetzt zurückholen“: one waiting mail into the inbox at once."""
    notaus.stop("aktion", uid)
    who = profiles.log_name(profiles.by_id(uid))
    mid = tidy.clean_mid(mid)
    if not mid or mid not in {x["mid"] for x in items(uid)}:
        print(f"mail: later back refused, not waiting | {who}", flush=True)
        raise LookupError("this mail does not wait")
    if not bring(uid, {mid}):
        print(f"mail: later back failed | {who}", flush=True)
        raise LookupError("the mail could not be brought back")
    print(f"mail: later back now | {who}", flush=True)
    return {"done": "back", "mid": mid}


def due(now=None):
    """Every minute: each profile's due mails back (also when the switch is off now, so none stays away)."""
    n = 0
    for p in profiles.names():
        uid = p.get("id")
        if uid and items(uid):
            try:
                n += bring(uid, now=now)
            except Exception as e:
                print(f"mail: later failed ({type(e).__name__}) | {profiles.log_name(p)}", flush=True)
    return n


def forget(uid):
    """The profile or its last mailbox is gone: the list goes (the mails stay in „Später“ on the mail server)."""
    STORE.forget(uid)


mail.ON_FORGET.append(forget)
mail.LIVE["spaeter"] = lambda: for_live()


def for_live():
    """Zustand → Live, node E-Mail: on or off, how many wait, how many came back today (numbers only)."""
    c = _count.counts()
    waiting = sum(len(STORE.mem.get(u, {}).get("v") or []) for u in list(STORE.mem))
    return {"on": bool(features.chat_cfg().get("mail_later")), "wait": waiting, "back": c["zurueck"], "put": c["gelegt"]}


# ---------------------------------------------------------------- API (page E-Mail, apps)
from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402

import guard  # noqa: E402
from core import assistant, json_body, own_profile  # noqa: E402

router = APIRouter()
MID = re.compile(r"<[^\s<>\"\\]{1,298}>")


def _mine(request, prof):
    guard.limit(request, "postordnen", prof["id"])
    if not features.allowed("mailspaeter", prof["id"]):
        print(f"mail: later refused, off | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(403, features.missing_text("mailspaeter", prof["id"]) or "Zurückstellen ist aus.")


@router.get("/api/profile/mail/snooze", dependencies=[Depends(assistant)])
def api_list(request: Request, prof=Depends(own_profile)):
    _mine(request, prof)
    return {"items": liste(prof["id"]), "when": list(WHEN)}


@router.post("/api/profile/mail/snooze", dependencies=[Depends(assistant)])
async def api_put(request: Request, prof=Depends(own_profile)):
    """{"id": "<account>:<uid>", "when": abend|morgen|wochenende|woche|at, "at": epoch seconds (with at)}"""
    _mine(request, prof)
    b = await json_body(request, 1024)
    who = profiles.log_name(prof)
    try:
        t = until(prof["id"], b.get("when") if b.get("when") in WHEN + ("at",) else "", b.get("at") or 0)
        return await asyncio.to_thread(put, prof["id"], str(b.get("id") or "")[:40], t)
    except LookupError:
        print(f"mail: later refused, gone | {who}", flush=True)
        raise HTTPException(404, "Die Mail ist nicht mehr im Posteingang.")
    except ValueError as e:
        print(f"mail: later refused, input | {who}", flush=True)
        raise HTTPException(400, str(e)[:200])
    except Exception as e:
        print(f"mail: later failed ({type(e).__name__}) | {who}", flush=True)
        raise HTTPException(502, "Das Postfach hat nicht geantwortet. Bitte gleich noch einmal.")


@router.post("/api/profile/mail/snooze/back", dependencies=[Depends(assistant)])
async def api_back(request: Request, prof=Depends(own_profile)):
    """„Jetzt zurückholen“: {"mid": Message-ID}"""
    guard.limit(request, "postordnen", prof["id"])
    b = await json_body(request, 1024)
    who = profiles.log_name(prof)
    mid = b.get("mid")
    if not isinstance(mid, str) or not MID.fullmatch(mid):
        print(f"mail: later back refused, input | {who}", flush=True)
        raise HTTPException(400, "mid")
    try:
        return await asyncio.to_thread(back_now, prof["id"], mid)
    except LookupError:
        raise HTTPException(404, "Diese Mail wartet nicht.")
