"""Bestätigungscodes (Dominik 2026-10-21 „5“, an idea seen in email-mcp, own code): a new mail with a confirmation code
(„482913 ist dein Bestätigungscode“) becomes a note on the device in use, with „Code kopieren“.

- Off until the admin switches chat.mail_code on (Funktionen → E-Mail lesen → Neue Mails sofort → „Bestätigungscodes“);
  it needs „Neue Mails sofort“ (mailidle.py), since a code is only useful within minutes. Then for every profile that
  may read mail (the admin can block single profiles), never for guests. A profile that used any device in the last
  mailidle.ACTIVE_SECONDS gets its IDLE connection for this, not only one that read its mail.
- Fixed rules of the panel, never the model: the mail is unread and at most AGE seconds old, its subject or text names
  a code (WORDS, not a voucher or an order number, NOT), and one token CODE stands close to that word; one note per
  mail, at most PER_HOUR notes an hour per profile.
- Never Telegram: the note goes to the device in use (push.pick); if that is Telegram, to the first other way of the
  profile (iPhone app, Android app, Spark-Begleiter, browser); with none there is no note. Apple carries only a fixed
  sentence (apns.py), the code waits on the Spark in memory for the note's own time; nothing is written to disk.
- Ablauf (pl_mail-Ideen 1, Dominik 2026-11-13 „1-7“): when the mail says how long the code is valid („gültig 10
  Minuten“, „bis 09:30 Uhr“, „expires in 15 minutes“; valid_until, fixed rules, counted from the mail's own time),
  the note is over then on every device (push.send bis) and is not followed up; a mail already past it makes no note.
  Without such words a note lives as before.
- The code is never logged and never on Live: lines carry fixed words and numbers, the profile only as
  profiles.log_name; Live (node E-Mail) shows notes today, a number.
"""
import asyncio
import datetime
import email.utils
import re
import threading
import time

import features
import notaus
import profiles
from common import DayCounter

AGE = 10 * 60        # seconds a mail may be old to count: a code is useless after a few minutes
PER_HOUR = 10        # notes per profile and hour
LOOK_MAX = 5         # new mails looked into for one arrival
TEXT_MAX = 4000      # characters of a mail's text that are searched
NEAR = 80            # characters after the word (or before it) the code may stand
NEAR_SHORT = 25      # a code of four digits only right after the word
TAG = "mailcode"

# what names a code; a voucher, discount, parcel or customer number is none (NOT)
WORDS = re.compile(r"(?i)(?<!\w)(best[äa]tigungs(?:code|nummer)|sicherheits(?:code|nummer)|verifizierungs?code|"
                   r"verifikationscode|anmelde-?code|login-?code|einmal-?(?:code|passwort|kennwort|pin)|zugangscode|"
                   r"sign[- ]?in code|log[- ]?in code|verification code|security code|confirmation code|access code|"
                   r"one[- ]time (?:code|password|passcode|pin)|passcode|otp|tan|code)(?!\w)")
NOT = re.compile(r"(?i)gutschein|rabatt|promo|coupon|voucher|discount|sendungs|tracking|kunden|bestell|rechnungs|"
                 r"artikel|postleitzahl|zip|qr|bar-?code|aktions")
CODE = re.compile(r"(?<![\w.,/:+€$#-])(\d{3}[ -]\d{3}|\d{4,8}|(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{6,8})"
                  r"(?![\w/:€$%-]|[.,]\d)")
YEAR = re.compile(r"(19|20)\d\d")
# how long the mail says the code is valid: minutes, or a clock time (VALID_AT); at most VALID_MAX minutes
VALID_MIN = re.compile(r"(?i)(?:gültig|gilt|läuft|verfällt|valid|expires?|expiring)[^.\n]{0,30}?(\d{1,4})\s*(?:min\b|minuten|minutes?)|"
                       r"(\d{1,4})\s*(?:min\b|minuten|minutes?)\s*(?:lang\s+)?(?:gültig|valid)")
VALID_AT = re.compile(r"(?i)(?:gültig bis|gilt bis|läuft um|verfällt um|valid until|expires at)\s*(?:um\s*)?([01]?\d|2[0-3])[:.]([0-5]\d)")
VALID_MAX = 24 * 60
COPY = re.compile(r"[A-Z0-9]{4,8}")    # what a note's first word may be for „Code kopieren“ (apps, Begleiter)

_said = {}           # uid -> {mail ids a note was made for} (memory only)
_hour = {}           # uid -> [times of notes]
_lock = threading.Lock()
_count = DayCounter(hinweise=0, abgelaufen=0)


def find(subject, text):
    """The code a mail names, by fixed rules (WORDS, NOT, CODE), without spaces or dashes; "" when there is none."""
    for source in (str(subject or "")[:300], str(text or "")[:TEXT_MAX]):
        for w in WORDS.finditer(source):
            if NOT.search(source[max(0, w.start() - 30):w.end() + 30]):
                continue
            after = [(m.start() - w.end(), m.group(1)) for m in CODE.finditer(source, w.end(), min(len(source), w.end() + NEAR))]
            before = [(w.start() - m.end(), m.group(1)) for m in CODE.finditer(source, max(0, w.start() - NEAR), w.start())]
            for gap, code in sorted(after) + sorted(before):
                plain = re.sub(r"[ -]", "", code)
                if len(plain) == 4 and (gap > NEAR_SHORT or YEAR.fullmatch(plain)):
                    continue
                return plain
    return ""


def valid_until(text, sent):
    """The time (epoch seconds) the code of a mail is over, by the mail's own words, counted from its time sent (an
    aware datetime); 0 when it says nothing usable. A clock time is the next such time after sent, in sent's zone."""
    text = str(text or "")[:TEXT_MAX]
    m = VALID_MIN.search(text)
    k = int(m.group(1) or m.group(2)) if m else 0
    if 1 <= k <= VALID_MAX:
        return sent.timestamp() + k * 60
    m = VALID_AT.search(text)
    if m:
        at = sent.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        if at <= sent:
            at += datetime.timedelta(days=1)
        return at.timestamp()
    return 0


def _way(uid):
    """The device for the note: the one in use (push.pick), never Telegram; "" when the profile has no other way."""
    import push
    kind, _ = push.pick(uid, True)
    if kind and kind != "tg":
        return kind
    have = push._have(uid, True)
    return next((k for k in ("app", "and", "desk", "web") if have[k]), "")


def _may(uid, now):
    with _lock:
        times = [t for t in _hour.get(uid, []) if now - t < 3600]
        if len(times) >= PER_HOUR:
            _hour[uid] = times
            return False
        _hour[uid] = times + [now]
        return True


def arrived(uid, now=None):
    """mailidle.on_new: a new mail came into one of the profile's inboxes (runs in the IDLE thread). Returns the
    number of notes."""
    import mail
    import push
    if not features.allowed("mailcode", uid) or notaus.blocks("auto", uid):
        return 0
    name = profiles.log_name(profiles.by_id(uid))
    now = time.time() if now is None else now
    try:
        found, _, _ = mail.find(uid, "", 1, True, 20, budget=60)
    except TimeoutError:
        print(f"mail: code too slow | {name}", flush=True)
        return 0
    with _lock:
        said = _said.setdefault(uid, set())
        fresh = [(f"{aid}:{u}", h) for aid, u, h in found if f"{aid}:{u}" not in said
                 and h.get("unread") and now - h["date"].timestamp() <= AGE][:LOOK_MAX]
        said.update(ref for ref, _ in fresh)
        if len(said) > 500:
            _said[uid] = {ref for ref, _ in fresh}
    notes = 0
    for ref, h in fresh:
        code, text = find(h.get("subject", ""), ""), ""
        if not code:
            try:
                msg = mail.message(uid, ref)
            except Exception as e:
                print(f"mail: code mail not readable ({type(e).__name__}) | {name}", flush=True)
                continue
            if msg is None:
                continue
            text = mail.plain(msg)[0]
            code = find(h.get("subject", ""), text)
        if not code:
            continue
        bis = valid_until(h.get("subject", "") + "\n" + text, h["date"])
        if bis and now >= bis:
            _count.bump("abgelaufen")
            print(f"mail: code expired | {name}", flush=True)
            continue
        way = _way(uid)
        if not way:
            print(f"mail: code no device | {name}", flush=True)
            continue
        if not _may(uid, now):
            print(f"mail: code limit | {PER_HOUR} an hour | {name}", flush=True)
            continue
        who = mail.known(uid, h.get("from", "")) or email.utils.parseaddr(h.get("from", ""))[1]
        who = re.sub(r"[^\w .&@-]", "", who.split(" <")[0])[:40].strip() or "?"
        asyncio.run(push.send(uid, "Bestätigungscode", f"{code} · {who}", tag=TAG, to=way, why="Bestätigungscode", bis=bis))
        _count.bump("hinweise")
        notes += 1
    print(f"mail: code looked | {len(fresh)} new, {notes} notes | {name}", flush=True)
    return notes


def wants_idle(uid, now=None):
    """mailidle.wanted: a profile with this function that used any device lately keeps its IDLE connection."""
    import mailidle
    now = time.time() if now is None else now
    t = profiles.LAST_USED.get(uid, ("", "", 0))[2]
    return t if now - t <= mailidle.ACTIVE_SECONDS and features.allowed("mailcode", uid) else 0


def for_live():
    """Zustand → Live, node E-Mail: on or off and notes today (a number, never a code or a sender)."""
    c = _count.counts()
    return {"on": bool(features.chat_cfg().get("mail_code")), "today": c["hinweise"], "over": c["abgelaufen"]}


def _hook():
    import mailidle
    mailidle.on_new(arrived)


_hook()
