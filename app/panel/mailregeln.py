"""Mail-Regeln (Mailclient Stufe B, Dominik 2026-10-19 „2a 3a“, plan kalender-mail/mailclient/plan.md): rules the
profile makes on the page E-Mail, like in a mail program. Part of „Mails ordnen“ (chat.mail_manage, off).

A rule is fixed data, never a model's guess:
  when   sender is an address, or ends on a domain; optionally the subject holds a word, the mail is to an
         address, or it has an attachment (the Content-Type header says multipart/mixed)
  then   move into a folder of that mailbox (one a message may go to: postfach._targets, never trash, junk, sent or
         drafts), mark it read, flag it (★), keep it out of „Für dich“

The first rule that fits decides (the profile orders them). Rules run each RUN_EVERY on mail that came into the
inbox since the last look (by UID, nothing older); a rule made from a mail can, with the code, also take the
mails already there (at most APPLY_MAX, „Rückgängig“ brings them back). A rule never deletes.

Regel-Vorschlag (Dominik 2026-10-20): every move on the page (postfach) counts per mailbox, sender address and
folder (learn); the LEARN_AFTER-th move within LEARN_DAYS asks once on the page whether a rule should do it, unless a
rule for that sender and folder is there or the profile said „Nicht mehr fragen“ (never). The counts sit in the same
file as the rules; only the page's own moves count, never a rule's or the tidying's.

Merkliste und kein Ping-Pong (Dominik 2026-10-30 „nach Empfehlung umsetzen“, plan mail-lernen 1a + 2a, a fix without
a switch): every mail a rule moves is remembered with its Message-ID, mailbox, folder, rule and time for tidy.LOG_DAYS
(at most tidy.LOG_MAX, in the same file). spark_moved is the one list of both sorters (the rules' list and the log of
„Mails aufräumen“); user_moved asks it whether the Spark moved a mail and the person put it somewhere else since (back
into the inbox with a new UID, same Message-ID). Such a mail no rule and no tidying ever touches again.

Sortieren aus Korrekturen lernen (Dominik 2026-10-30 „nach Empfehlung umsetzen“, plan mail-lernen 3a + 4a + 5a, admin switch
chat.mail_learn under Mails ordnen, off; no switch of the profile, guests never): a mail the Spark sorted (spark_moved)
that the person took out of where it put it is a correction (correct, kept as „fixes“ for FIX_DAYS in the same file):
  - seen at once on the page E-Mail (page_moved: the panel knows where it came from), in the inbox at the next look of
    the rules (run) or of „Mails aufräumen“, below the KI folder in the night look (suggest, only when a folder changed)
  - into the fixed folder „<KI folder>/Falsch sortiert“ (tidy.WRONG, made when the function is on) = „war falsch“
    without a goal; into another folder = a correction with its goal; back into the inbox = the inbox
  - fixed thresholds, never the model: the mail itself is never touched again (Stufe 1); FIX_EXCEPT correction of a
    sender makes it an exception of the rule (fits skips it); FIX_PAUSE corrections of one rule in FIX_DAYS pause it
    (on false, "paused") with a card; a correction with a goal counts FIX_WEIGHT times in learn, so the known card
    „Regel-Vorschlag“ asks at once („Regel ändern“, „Nur Ausnahme“, „Nicht mehr fragen“); a mail in „Falsch sortiert“
    gets the card „Wohin gehört diese Mail?“ with the sender's usual folders, the inbox and „Anderer Ordner …“
Only headers (sender address, Message-ID) are compared; nothing goes to the model; the journal carries fixed words and
numbers only.

Mail-Statistik (Dominik 2026-10-21 „6“): stats() counts who writes most in 30 days and the mails a week, from the
listing the Mail-Vorrat keeps; the tab Regeln shows it with „Regel …“ per sender.

What comes in is data: sender, subject and addresses are only compared with the rule's words (casefold, no regular
expressions from the profile). The rules live in users/<id>/mail-regeln.json (600); the journal carries fixed words
and numbers only (never a sender, subject, folder or word of a rule); Live shows rules and how many mails they took.
"""
import email.utils
import imaplib
import json
import os
import re
import secrets
import threading
import time

import features
import mail
import notaus
import profiles
import tidy
from common import DayCounter, write_json

FILE = "mail-regeln.json"
MAX_RULES = 100
RUN_EVERY = 300          # seconds between two looks at the inbox of a profile with rules
NEW_MAX = 200            # new mails one look takes at most per mailbox
PREVIEW_DAYS = 90
PREVIEW_MAX = 1000       # newest inbox mails a dry run looks at
APPLY_MAX = 50           # mails „auch die vorhandenen“ takes at most (as many as „Rückgängig“ brings back)
WORD_MAX = 80
LEARN_AFTER = 3          # the third move of one sender into one folder brings the hint
LEARN_DAYS = 30          # moves older than this do not count
LEARN_MAX = 300          # counted sender/folder pairs per profile (the oldest go)
HEAD = "FROM TO CC SUBJECT CONTENT-TYPE MESSAGE-ID"
# Regel-Vorschläge aus dem Ablegen (Dominik 2026-10-21 „ok“, plan plaene/mail-regeln-lernen.md): fixed thresholds
SUGGEST_NIGHT = (2, 5)   # local hours of the night look
SUGGEST_MIN = 5          # mails of one sender in one folder at the least
SUGGEST_SHARE = 0.8      # and this share of all its mails there (the folders under the KI folder and the inbox)
SUGGEST_DAY = 3          # new suggestions per night at most
SUGGEST_KEEP = 7         # days an unanswered suggestion stays
SUGGEST_SCAN = 300       # newest mails per folder looked at
SUGGEST_MAX = 20         # open suggestions per profile
# Sortieren aus Korrekturen lernen (plan mail-lernen 3a + 4a + 5a, chat.mail_learn): the fixed thresholds, only here
FIX_EXCEPT = 1           # corrections of one sender against one rule that make the sender an exception of it
FIX_PAUSE = 3            # corrections of one rule within FIX_DAYS that pause it (and bring a card)
FIX_DAYS = 30            # corrections older than this do not count and go
FIX_WEIGHT = 3           # a correction with a goal counts this often in learn (one is enough for the card)
FIX_MAX = 500            # corrections kept per profile
EXCEPT_MAX = 50          # exceptions per rule
WOHIN_MAX = 3            # folder buttons on the card „Wohin gehört diese Mail?“
FREEMAIL = ("gmail.com", "googlemail.com", "gmx.de", "gmx.net", "gmx.at", "gmx.ch", "web.de", "t-online.de", "icloud.com",
            "me.com", "mac.com", "outlook.com", "outlook.de", "hotmail.com", "hotmail.de", "live.com", "live.de", "yahoo.com",
            "yahoo.de", "aol.com", "freenet.de", "posteo.de", "mailbox.org", "proton.me", "protonmail.com", "online.de")
_lock = threading.Lock()
_last = {}               # uid -> when its rules last ran
_sug_day = {}            # uid -> the night its rule suggestions were looked for
_count = DayCounter(genommen=0, laeufe=0, vorschlaege=0, nacht=0, statistik=0, zurueck=0, korrektur=0, ausnahme=0, pausiert=0)
# per day: mails taken, looks, rule hints, night suggestions, statistics shown, mails the person put back, corrections,
# exceptions made by them, rules paused by them


def _file(uid):
    return profiles._path(uid, FILE)


def load(uid):
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
        d = d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        d = {}
    rules = d.get("rules") if isinstance(d.get("rules"), list) else []
    d["rules"] = [r for r in rules if isinstance(r, dict) and isinstance(r.get("id"), str)][:MAX_RULES]
    d["seen"] = d.get("seen") if isinstance(d.get("seen"), dict) else {}
    d["learn"] = d.get("learn") if isinstance(d.get("learn"), dict) else {}
    d["never"] = [k for k in (d.get("never") if isinstance(d.get("never"), list) else []) if isinstance(k, str)][-LEARN_MAX:]
    d["suggest"] = [x for x in (d.get("suggest") if isinstance(d.get("suggest"), list) else [])
                    if isinstance(x, dict) and isinstance(x.get("id"), str)][-SUGGEST_MAX:]
    d["looked"] = d.get("looked") if isinstance(d.get("looked"), dict) else {}
    cut = time.time() - tidy.LOG_DAYS * 86400
    d["moved"] = [x for x in (d.get("moved") if isinstance(d.get("moved"), list) else [])
                  if isinstance(x, dict) and isinstance(x.get("mid"), str) and x["mid"]
                  and isinstance(x.get("t"), int) and x["t"] > cut][-tidy.LOG_MAX:]
    fcut = time.time() - FIX_DAYS * 86400
    d["fixes"] = [x for x in (d.get("fixes") if isinstance(d.get("fixes"), list) else [])
                  if isinstance(x, dict) and isinstance(x.get("mid"), str) and x["mid"]
                  and isinstance(x.get("t"), int) and x["t"] > fcut][-FIX_MAX:]
    for r in d["rules"]:
        if not isinstance(r.get("except"), list):
            r.pop("except", None)
    return d


def _save(uid, d):
    write_json(_file(uid), d, mode=0o600, dir_mode=0o700)


def _word(v, most=WORD_MAX):
    return re.sub(r"[\x00-\x1f\x7f]", "", str(v or "")).strip()[:most]


def clean(uid, body):
    """A rule from the page, checked: ValueError for anything that is not one."""
    accts = {a["id"] for a in mail.get(uid)["accounts"]}
    w = body.get("when") if isinstance(body.get("when"), dict) else {}
    t = body.get("then") if isinstance(body.get("then"), dict) else {}
    sender = _word(w.get("from")).lower()
    if sender.startswith("@"):
        sender = "@" + sender[1:].lstrip("@")
    if sender and not re.fullmatch(r"(@[\w.\-]+\.\w{2,}|[^@\s<>\"]{1,64}@[\w.\-]+\.\w{2,})", sender):
        raise ValueError("sender: an address (anna@x.de) or a domain (@x.de)")
    to = _word(w.get("to")).lower()
    if to and not re.fullmatch(r"[^@\s<>\"]{1,64}@[\w.\-]+\.\w{2,}", to):
        raise ValueError("to: an address")
    subject = _word(w.get("subject"))
    attach = bool(w.get("attach"))
    if not (sender or to or subject):
        raise ValueError("a rule needs a sender, a recipient or a word of the subject")
    account = str(body.get("account") or "")
    if account and account not in accts:
        raise ValueError("unknown mailbox")
    folder = _word(t.get("folder"), 200)
    if folder and not account:
        raise ValueError("a folder belongs to one mailbox: pick the mailbox")
    then = {"folder": folder, "read": bool(t.get("read")), "flag": bool(t.get("flag")), "quiet": bool(t.get("quiet"))}
    if not (then["folder"] or then["read"] or then["flag"] or then["quiet"]):
        raise ValueError("a rule needs something to do")
    return {"account": account, "when": {"from": sender, "to": to, "subject": subject, "attach": attach},
            "then": then, "on": body.get("on") is not False}


def add(uid, body, rid=""):
    """A new rule (at the end) or, with rid, the rule changed in place; returns the rule."""
    r = clean(uid, body)
    if r["then"]["folder"]:
        _check_folder(uid, r["account"], r["then"]["folder"])
    with _lock:
        d = load(uid)
        if rid:
            old = next((x for x in d["rules"] if x["id"] == rid), None)
            if not old:
                raise LookupError("no such rule")
            old.update(r)
            if r["on"]:
                old.pop("paused", None)      # switched on again: the pause of the corrections is over
            r = old
        else:
            if len(d["rules"]) >= MAX_RULES:
                raise ValueError(f"at most {MAX_RULES} rules")
            r.update(id=secrets.token_hex(4), made=int(time.time()), n={})
            d["rules"].append(r)
        gone = [x["id"] for x in d["suggest"] if x["account"] == r["account"] and x["from"] == r["when"]["from"]
                and x.get("kind", "fix") == "fix"]
        gone += [x["id"] for x in d["suggest"] if x.get("kind") == "pause" and x.get("rid") == r["id"] and r["on"]]
        d["suggest"] = [x for x in d["suggest"] if x["id"] not in gone]
        _save(uid, d)
    _cards_done(uid, gone, "erledigt")
    return r


def _check_folder(uid, account, folder):
    import postfach
    acct = next((a for a in mail.get(uid)["accounts"] if a["id"] == account), None)
    if not acct:
        raise ValueError("unknown mailbox")
    with tidy.Box(acct) as box:
        targets, _ = postfach._targets(box)
    if folder not in targets:
        raise ValueError("not a folder a message may go to")


def _key(account_id, sender, folder):
    return f"{account_id}|{sender}|{folder}"


def learn(uid, account_id, senders, folder, now=None, weight=1):
    """Counts the page's moves of these senders into `folder`; {"account", "from", "folder", "n"} for the hint when
    one sender reached LEARN_AFTER moves within LEARN_DAYS (and is then counted from zero again), else None.
    weight: a correction counts FIX_WEIGHT times (Sortieren aus Korrekturen lernen)."""
    now = int(now or time.time())
    if not senders or not folder:
        return None
    hint = None
    with _lock:
        d = load(uid)
        learnt = {k: v for k, v in d["learn"].items()
                  if isinstance(v, list) and len(v) == 2 and now - int(v[1]) < LEARN_DAYS * 86400}
        ruled = {(r.get("account", ""), r["when"].get("from", ""), r["then"].get("folder", "")) for r in d["rules"]}
        for a in dict.fromkeys(senders):
            k = _key(account_id, a, folder)
            n = (learnt.get(k) or [0, now])[0] + max(1, int(weight))
            learnt[k] = [n, now]
            if n >= LEARN_AFTER and not hint and k not in d["never"] and (account_id, a, folder) not in ruled:
                hint = {"account": account_id, "from": a, "folder": folder, "n": n}
                learnt[k] = [0, now]
        d["learn"] = dict(sorted(learnt.items(), key=lambda kv: kv[1][1])[-LEARN_MAX:])
        _save(uid, d)
    if hint:
        _count.bump("vorschlaege")
        print(f"mail: rule hint | {hint['n']} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return hint


def never(uid, body):
    """„Nicht mehr fragen“ on a hint: this sender into this folder never asks again."""
    accts = {a["id"] for a in mail.get(uid)["accounts"]}
    account, sender, folder = str(body.get("account") or ""), _word(body.get("from")).lower(), _word(body.get("folder"), 200)
    if account not in accts or not sender or not folder:
        raise ValueError("mailbox, sender and folder")
    with _lock:
        d = load(uid)
        k = _key(account, sender, folder)
        d["never"] = [x for x in d["never"] if x != k][-(LEARN_MAX - 1):] + [k]
        d["learn"].pop(k, None)
        gone = [x["id"] for x in d["suggest"] if _key(x["account"], x["from"], x["folder"]) == k]
        d["suggest"] = [x for x in d["suggest"] if x["id"] not in gone]
        _save(uid, d)
    _cards_done(uid, gone, "ausblenden")
    print(f"mail: rule hint never | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return {"ok": True}


def remove(uid, rid):
    with _lock:
        d = load(uid)
        n = len(d["rules"])
        d["rules"] = [r for r in d["rules"] if r["id"] != rid]
        if len(d["rules"]) == n:
            return False
        if not d["rules"]:
            d["seen"] = {}
        gone = [x["id"] for x in d["suggest"] if x.get("rid") == rid and x.get("kind") in ("fix", "pause")]
        d["suggest"] = [x for x in d["suggest"] if x["id"] not in gone]
        _save(uid, d)
    _cards_done(uid, gone, "erledigt")
    return True


def order(uid, ids):
    """The rules in the order of ids (the first that fits decides); rules not named keep their place at the end."""
    with _lock:
        d = load(uid)
        pos = {rid: i for i, rid in enumerate(ids)}
        d["rules"].sort(key=lambda r: pos.get(r["id"], len(pos)))
        _save(uid, d)
    return d["rules"]


def forget(uid):
    """Ich → Meine Daten / profile removed: the rules go."""
    try:
        os.remove(_file(uid))
    except OSError:
        pass


def public(uid):
    """The tab Regeln: own rules with how many mails each took this month (numbers), and the sender rules of
    „Mails aufräumen“ (tidy.py), shown here too and deleted there."""
    d = load(uid)
    month = time.strftime("%Y-%m")
    names = {a["id"]: a.get("name", "") for a in mail.get(uid)["accounts"]}
    rules = [dict(r, month=int((r.get("n") or {}).get(month, 0)), box=names.get(r.get("account"), "")) for r in d["rules"]]
    for r in rules:
        r.pop("n", None)
    try:
        st = tidy.state(uid)
        old = [{"id": r["id"], "match": r["match"], "folder": tidy.folder_of(st, r["cat"]) if r["cat"] != "keep" else "",
                "keep": r["cat"] == "keep"} for r in st["rules"]]
    except Exception:
        old = []
    sug = [{k: x.get(k, 0) for k in ("id", "account", "from", "folder", "n", "inbox")} | {"box": names.get(x["account"], "")}
           for x in _fresh(d["suggest"]) if x["account"] in names and x.get("kind", "fix") == "fix"]
    return {"rules": rules, "tidy": old, "accounts": [{"id": k, "name": v} for k, v in names.items()], "suggest": sug}


# ---------------------------------------------------------------- deciding
def _addrs(v):
    return [a.lower() for _, a in email.utils.getaddresses([str(v or "")]) if a]


def fits(rule, h):
    """Does the rule fit a message's header h ({from, to: [..], subject, attach})? Words compared, never run. A sender
    on the rule's exceptions (Sortieren aus Korrekturen lernen) never fits it."""
    w = rule["when"]
    if h["from"] and h["from"] in (rule.get("except") or ()):
        return False
    s = w.get("from") or ""
    if s:
        if s.startswith("@"):
            dom = h["from"].split("@")[-1]
            if not (dom == s[1:] or dom.endswith("." + s[1:])):
                return False
        elif h["from"] != s:
            return False
    if w.get("to") and w["to"] not in h["to"]:
        return False
    if w.get("subject") and w["subject"].casefold() not in h["subject"].casefold():
        return False
    if w.get("attach") and not h["attach"]:
        return False
    return True


def first(rules, h, account):
    return next((r for r in rules if r.get("on", True) and (not r.get("account") or r["account"] == account)
                 and fits(r, h)), None)


def head(msg):
    return {"from": (_addrs(msg.get("From", "")) or [""])[0], "to": _addrs(msg.get("To", "")) + _addrs(msg.get("Cc", "")),
            "subject": mail._hdr(msg.get("Subject", "")),
            "attach": mail.has_attach(msg),
            "mid": tidy.clean_mid(msg.get("Message-ID", ""))}


def quiet(uid, sender, subject):
    """Für dich (fuerdich.py): a rule says „nicht in Für dich“ for this mail."""
    rules = [r for r in load(uid)["rules"] if r.get("on", True) and r["then"].get("quiet")]
    if not rules:
        return False
    h = {"from": (_addrs(sender) or [""])[0], "to": [], "subject": subject or "", "attach": False}
    return any(fits(dict(r, when=dict(r["when"], to="", attach=False)), h) for r in rules)


def _do(box, targets, rule, uids):
    """One rule's actions on messages of the selected inbox; returns the Message-IDs of what was moved."""
    import postfach
    t = rule["then"]
    if t.get("read"):
        postfach._store(box, uids, "read")
    if t.get("flag"):
        postfach._store(box, uids, "flag")
    if t.get("folder"):
        if t["folder"] not in targets:
            raise ValueError("the rule's folder is gone")
        heads = box.headers(uids, "MESSAGE-ID")
        mids = [str(h.get("Message-ID") or "").strip()[:300] for h in heads.values()]
        postfach._move(box, uids, t["folder"])
        return [m for m in mids if m]
    return []


# ---------------------------------------------------------------- Merkliste (plan mail-lernen 1a + 2a)
def _remember(uid, aid, rule, mids):
    """What a rule moved: {mid, aid, folder, rid, t} per mail, only the Message-ID of the mail (no sender, no subject)."""
    mids = [m for m in (tidy.clean_mid(x) for x in mids) if m]
    if not mids:
        return
    now = int(time.time())
    with _lock:
        d = load(uid)
        d["moved"] = (d["moved"] + [{"mid": m, "aid": aid, "folder": rule["then"].get("folder", ""), "rid": rule["id"], "t": now}
                                    for m in mids])[-tidy.LOG_MAX:]
        _save(uid, d)


def spark_moved(uid, aid, d=None, st=None):
    """The one list of both sorters: {Message-ID: entry with "by" ("rule" or "tidy") and "folder"} of every mail of this
    mailbox the Spark moved itself in the last tidy.LOG_DAYS: the Mail-Regeln (their list here) and „Mails aufräumen“
    (its log; an entry brought back with „Zurück“ wins and carries "undone"). d and st when the caller has them."""
    d = load(uid) if d is None else d
    st = tidy.state(uid) if st is None else st
    out = {x["mid"]: dict(x, by="rule") for x in d["moved"] if x.get("aid") == aid}
    for x in st["log"]:
        if x.get("aid") == aid and x.get("mid"):
            if x.get("undone") or not out.get(x["mid"], {}).get("undone"):
                out[x["mid"]] = dict(x, by="tidy")
    return out


def user_moved(moved, mid, where):
    """Did the Spark move this mail, and did the person put it somewhere else since (`where`, the inbox above all)?
    Its entry of spark_moved, else None. Such a mail no sorter touches again (no ping-pong)."""
    x = moved.get(mid) if mid else None
    return x if x and (x.get("undone") or x.get("folder") != where) else None


def mark_back(uid, mids):
    """Mails a rule moved that the person put back: marked once (counted for Live). Returns how many were new."""
    mids = set(mids)
    if not mids:
        return 0
    now, n = int(time.time()), 0
    with _lock:
        d = load(uid)
        for x in d["moved"]:
            if x["mid"] in mids and not x.get("back"):
                x["back"], n = now, n + 1
        if n:
            _save(uid, d)
    if n:
        _count.bump("zurueck", n)
    return n


# ---------------------------------------------------------------- Sortieren aus Korrekturen lernen (plan mail-lernen 3a + 4a + 5a)
def wrong_path(st):
    """„<KI folder>/Falsch sortiert“ (tidy.WRONG) in our "/" spelling; the name is fixed, never from a mail."""
    return f"{st['root']}/{tidy.WRONG}" if st.get("root") else tidy.WRONG


def ensure_wrong(uid, box, st=None):
    """The folder „Falsch sortiert“ under the KI folder of this mailbox, made once (and the KI folder with it) when it is
    missing; its server name. Making these two folders is the only thing it writes; never a folder of the mail program."""
    st = tidy.state(uid) if st is None else st
    name = box.name(wrong_path(st))
    if name in box.boxes:
        return name
    for p in ([box.name(st["root"])] if st.get("root") else []) + [name]:
        if p in box.boxes:
            continue
        if box.is_special(p):
            raise ValueError("a folder of the mail program")
        typ, _ = box.c.create(tidy._q(tidy._utf7(p)))
        if typ != "OK" and p == name:
            print(f"mail: rule wrong folder | refused | {profiles.log_name(profiles.by_id(uid))}", flush=True)
            raise ValueError("the folder for wrongly sorted mail could not be made")
        try:
            box.c.subscribe(tidy._q(tidy._utf7(p)))
        except Exception:
            pass
        box.boxes[p] = {"raw": tidy._utf7(p), "flags": ""}
    print(f"mail: rule wrong folder | made | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return name


def _srv(box, x):
    """Where the Spark put a mail of spark_moved, in the server's own folder name (the tidy log keeps "KI/Werbung")."""
    return box.name(x.get("folder", "")) if x.get("by") == "tidy" else x.get("folder", "")


def found(box, x, sender, nach):
    """One correction for correct(): the entry x of spark_moved, the sender address, where it lies now (a folder, "INBOX",
    or "" for „Falsch sortiert“)."""
    return {"mid": x.get("mid", ""), "by": x.get("by", "rule"), "rid": x.get("rid", "") if x.get("by") == "rule" else "",
            "von": _srv(box, x), "from": str(sender or "").lower()[:200], "nach": nach}


def correct(uid, aid, fixes, usual=None, now=None):
    """The person corrected the Spark (fixes from found()). Fixed rules, never the model: one correction per mail (a mail
    in „Falsch sortiert“ put into a folder later gets its goal); FIX_EXCEPT of a sender against a rule → exception;
    FIX_PAUSE of a rule in FIX_DAYS → paused with a card; a goal counts FIX_WEIGHT times in learn → the card
    „Regel-Vorschlag“; „Falsch sortiert“ → the card „Wohin gehört diese Mail?“. usual: {sender: {folder: n}} seen in
    the night (for the card's folder buttons). Returns {"new": n, "placed": n}."""
    if not fixes or not features.allowed("maillearn", uid):
        return {"new": 0, "placed": 0}
    now = int(now or time.time())
    who = profiles.log_name(profiles.by_id(uid))
    made, placed, paused, excepted = [], [], [], 0
    with _lock:
        d = load(uid)
        have = {(f.get("aid"), f["mid"]): f for f in d["fixes"]}
        rules = {r["id"]: r for r in d["rules"]}
        for x in fixes:
            if not x.get("mid"):
                continue
            old = have.get((aid, x["mid"]))
            if old:
                if old.get("nach") == "" and x["nach"] not in ("", old.get("von")):   # placed out of „Falsch sortiert“
                    old["nach"] = x["nach"]
                    placed.append(old)
                continue
            how = "wrong" if not x["nach"] else "inbox" if x["nach"].upper() == "INBOX" else "folder"
            f = {"id": secrets.token_hex(4), "mid": x["mid"], "aid": aid, "by": x["by"], "rid": x["rid"], "von": x["von"],
                 "nach": x["nach"], "how": how, "from": x["from"], "t": now}
            d["fixes"].append(f)
            have[(aid, x["mid"])] = f
            made.append(f)
            r = rules.get(f["rid"]) if f["rid"] else None
            if r is None:
                continue
            mine = [y for y in d["fixes"] if y.get("rid") == r["id"] and now - y["t"] < FIX_DAYS * 86400]
            exc = r.get("except") or []
            if f["from"] and sum(1 for y in mine if y.get("from") == f["from"]) >= FIX_EXCEPT \
                    and f["from"] not in exc and len(exc) < EXCEPT_MAX:
                r["except"] = exc + [f["from"]]
                f["exc"] = True
                excepted += 1
            if len(mine) >= FIX_PAUSE and r.get("on", True):
                r["on"], r["paused"] = False, now
                paused.append((r["id"], len(mine)))
        d["fixes"] = d["fixes"][-FIX_MAX:]
        _save(uid, d)
    for how in ("inbox", "folder", "wrong"):
        n = sum(1 for f in made if f["how"] == how)
        if n:
            print(f"mail: rule correction | {how} | {n} | {who}", flush=True)
    if placed:
        print(f"mail: rule correction | placed | {len(placed)} | {who}", flush=True)
    if excepted:
        print(f"mail: rule exception | {excepted} | {who}", flush=True)
    for _, n in paused:
        print(f"mail: rule paused | {n} | {who}", flush=True)
    _count.bump("korrektur", len(made))
    _count.bump("ausnahme", excepted)
    _count.bump("pausiert", len(paused))
    # the cards (vorgaenge, kind "regel"): the known Regel-Vorschlag for a goal, „Wohin …?“ for „Falsch sortiert“, a pause
    sug, open_ = [], {(x["from"], x["folder"]) for x in load(uid)["suggest"] if x.get("kind") == "fix" and x["account"] == aid}
    for f in [f for f in made + placed if f["nach"] and f["nach"].upper() != "INBOX" and f["from"]]:
        if (f["from"], f["nach"]) in open_:
            continue        # one card for one sender and folder, also for several mails at once
        open_.add((f["from"], f["nach"]))
        if learn(uid, aid, [f["from"]], f["nach"], now, FIX_WEIGHT):
            sug.append({"kind": "fix", "account": aid, "from": f["from"], "folder": f["nach"], "von": f["von"],
                        "rid": f["rid"], "n": FIX_WEIGHT, "inbox": 0})
    d = load(uid)
    for f in [f for f in made if f["how"] == "wrong" and f["from"]]:
        if _key(aid, f["from"], "") in d["never"] or any(x.get("mid") == f["mid"] for x in d["suggest"]):
            continue
        sug.append({"kind": "wohin", "account": aid, "from": f["from"], "folder": "", "von": f["von"], "rid": f["rid"],
                    "mid": f["mid"], "inbox": 0, "n": 0,
                    "ziele": _ziele(d, aid, f["from"], {f["von"], ""}, (usual or {}).get(f["from"]))})
    for rid, n in paused:
        sug.append({"kind": "pause", "account": aid, "from": "", "folder": "", "rid": rid, "n": n, "inbox": 0})
    if sug:
        for x in sug:
            x.update(id=secrets.token_hex(4), t=now)
        with _lock:
            d = load(uid)
            gone = {x["id"] for x in d["suggest"]}
            d["suggest"] = (d["suggest"] + sug)[-SUGGEST_MAX:]
            _save(uid, d)
        wohin = sum(1 for x in sug if x["kind"] == "wohin")
        for x in sug:
            _card(uid, x, say=x["kind"] != "wohin" or wohin == 1)
        _cards_done(uid, [i for i in gone if i not in {x["id"] for x in d["suggest"]}], "abgelaufen")
    return {"new": len(made), "placed": len(placed)}


def _ziele(d, aid, sender, skip, seen=None):
    """The card's folder buttons: the folders this sender's mails usually go to (the page's moves, the corrections, the
    rules for it, what the night saw), most first, at most WOHIN_MAX; never the one it came from."""
    n = dict(seen or {})
    for k, v in d["learn"].items():
        a, s, f = (k.split("|", 2) + ["", ""])[:3]
        if a == aid and s == sender and isinstance(v, list) and v:
            n[f] = n.get(f, 0) + max(1, int(v[0]))
    for x in d["fixes"]:
        if x.get("aid") == aid and x.get("from") == sender and x.get("nach"):
            n[x["nach"]] = n.get(x["nach"], 0) + FIX_WEIGHT
    for r in d["rules"]:
        if r.get("account") == aid and r["when"].get("from") == sender and r["then"].get("folder"):
            n[r["then"]["folder"]] = n.get(r["then"]["folder"], 0) + 1
    return [f for f, _ in sorted(n.items(), key=lambda kv: (-kv[1], kv[0]))
            if f and f not in skip and f.upper() != "INBOX"][:WOHIN_MAX]


def page_moved(uid, box, aid, src, dst, pairs):
    """postfach: the person moved mails [(Message-ID, sender)] from src to dst on the page (box still open). With the
    function on, a mail the Spark sorted and the person took out of where it put it (or out of „Falsch sortiert“) is a
    correction; the others count for the hint as before (learn). Returns the hint for the page or None."""
    if not features.allowed("maillearn", uid):
        return learn(uid, aid, [a for _, a in pairs if a], dst) if dst else None
    st = tidy.state(uid)
    wrong = box.name(wrong_path(st))
    moved = spark_moved(uid, aid, st=st)
    fixes, rest = [], []
    for mid, sender in pairs:
        x = moved.get(tidy.clean_mid(mid))
        von = _srv(box, x) if x and not x.get("undone") else None
        if von is not None and src in (von, wrong) and dst != von:
            fixes.append(found(box, x, sender, "" if dst == wrong else dst))
        elif sender:
            rest.append(sender)
    if fixes:
        correct(uid, aid, fixes)
    return learn(uid, aid, rest, dst) if rest and dst and dst != wrong else None


def fixed_senders(uid, aid):
    """„Mails aufräumen“ (tidy._run): {sender: time of its last correction} of what it sorted and the person corrected in
    FIX_DAYS; such a sender is asked about instead of moved until a newer rule of the profile decides."""
    if not features.allowed("maillearn", uid):
        return {}
    out = {}
    for x in load(uid)["fixes"]:
        if x.get("aid") == aid and x.get("by") == "tidy" and x.get("from"):
            out[x["from"]] = max(out.get(x["from"], 0), x["t"])
    return out


def _place(uid, aid, mid, dst):
    """A button of „Wohin gehört diese Mail?“: exactly this mail (its Message-ID) from „Falsch sortiert“ into dst, a
    folder a message may go to or the inbox. LookupError when it is not there any more."""
    import postfach
    notaus.stop("aktion", uid)
    acct = postfach._acct(uid, aid)
    with tidy.Box(acct) as box:
        targets, _ = postfach._targets(box)
        src = box.name(wrong_path(tidy.state(uid)))
        if src not in box.boxes:
            raise LookupError("no such folder")
        if dst.upper() != "INBOX" and dst not in targets:
            raise ValueError("not a folder a message may go to")
        box.select(src, write=True)
        hits = box.find_mid(mid)
        if len(hits) != 1:
            raise LookupError("the message is not there")
        postfach._move(box, hits, "INBOX" if dst.upper() == "INBOX" else dst)
    print(f"mail: rule card place | 1 | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    postfach._tree_old(uid)
    mail.changed(uid, "", "back")


def _bump(uid, rid, n):
    with _lock:
        d = load(uid)
        month = time.strftime("%Y-%m")
        for r in d["rules"]:
            if r["id"] == rid:
                r["n"] = {month: int((r.get("n") or {}).get(month, 0)) + n}
        _save(uid, d)
    _count.bump("genommen", n)


def run(uid, now=None):
    """Applies the profile's rules to what came into each inbox since the last look. {"taken": n, "errors": n}."""
    import postfach
    d = load(uid)
    rules = [r for r in d["rules"] if r.get("on", True)]
    taken = errors = 0
    if not rules:
        return {"taken": 0, "errors": 0}
    notaus.stop("auto", uid)
    seen = dict(d["seen"])
    learn_on = features.allowed("maillearn", uid)
    for acct in mail.get(uid)["accounts"]:
        mine = [r for r in rules if not r.get("account") or r["account"] == acct["id"]]
        if not mine:
            continue
        fixes = []
        try:
            with tidy.Box(acct) as box:
                if learn_on:
                    ensure_wrong(uid, box)
                targets, _ = postfach._targets(box)
                v = box.select("INBOX", write=True)
                last = seen.get(acct["id"]) or {}
                uids = sorted(box.search("ALL"))
                if last.get("v") != v or not isinstance(last.get("uid"), int):
                    seen[acct["id"]] = {"v": v, "uid": uids[-1] if uids else 0}   # first look: nothing older
                    continue
                new = [u for u in uids if u > last["uid"]][:NEW_MAX]
                if not new:
                    continue
                heads = box.headers(new, HEAD)
                moved = spark_moved(uid, acct["id"], d)
                todo, back = {}, []
                for u in new:
                    if u in heads:
                        h = head(heads[u])
                        x = user_moved(moved, h["mid"], "INBOX")
                        if x:   # the Spark moved it, the person put it back: it stays
                            back.append(h["mid"])
                            if learn_on and not x.get("undone"):
                                fixes.append(found(box, x, h["from"], "INBOX"))
                            continue
                        r = first(mine, h, acct["id"])
                        if r:
                            todo.setdefault(r["id"], (r, []))[1].append(u)
                if back:
                    mark_back(uid, back)
                    print(f"mail: rule skip | user_moved | {len(back)} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
                for r, us in todo.values():
                    try:
                        _remember(uid, acct["id"], r, _do(box, targets, r, us))
                        _bump(uid, r["id"], len(us))
                        taken += len(us)
                    except (ValueError, OSError) as e:
                        errors += 1
                        print(f"mail: rule failed ({type(e).__name__}) | {profiles.log_name(profiles.by_id(uid))}", flush=True)
                seen[acct["id"]] = {"v": v, "uid": new[-1]}
        except (OSError, ValueError, imaplib.IMAP4.error) as e:
            errors += 1
            print(f"mail: rules not run ({type(e).__name__}) | {profiles.log_name(profiles.by_id(uid))}", flush=True)
        if fixes:
            correct(uid, acct["id"], fixes)
    with _lock:
        d = load(uid)
        d["seen"] = seen
        _save(uid, d)
    _count.bump("laeufe")
    print(f"mail: rules run | {taken} taken, {errors} errors | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    if taken:
        mail.changed(uid, "", "back")   # the cached inbox listing is fetched anew
    return {"taken": taken, "errors": errors}


# ---------------------------------------------------------------- Regel-Vorschläge aus dem Ablegen
def _fresh(sug, now=None):
    now = time.time() if now is None else now
    return [x for x in sug if now - int(x.get("t", 0)) < SUGGEST_KEEP * 86400]


def _under(box, root):
    """The folders below the profile's KI folder („Mails aufräumen“, tidy root) in the server's own names."""
    if not root:
        return []
    top = box.name(root)
    return sorted(n for n, x in box.boxes.items() if n.startswith(top + box.delim) and "\\noselect" not in x["flags"])


def _status(box, name):
    """MESSAGES and UIDNEXT of a folder: when both stay, nothing was put in or taken out since."""
    raw = box.boxes.get(name, {}).get("raw") or tidy._utf7(name)
    typ, data = box.c.status(tidy._q(raw), "(MESSAGES UIDNEXT)")
    text = b" ".join(x for x in data if isinstance(x, bytes)).decode(errors="replace") if typ == "OK" else ""
    return "/".join(re.findall(r"(?:MESSAGES|UIDNEXT) (\d+)", text))


def _senders(box, name, days):
    """{sender address: [Message-ID, …]} of the newest SUGGEST_SCAN mails of the last days in a folder (header only)."""
    box.select(name)
    uids = sorted(box.search("SINCE", tidy._since(days)))[-SUGGEST_SCAN:]
    out = {}
    for h in box.headers(uids, "FROM MESSAGE-ID").values():
        a = (_addrs(h.get("From", "")) or [""])[0]
        if a:
            out.setdefault(a, []).append(tidy.clean_mid(h.get("Message-ID", "")))
    return out


def _weigh(count, inbox, own, skip):
    """Fixed rules (never the model): [(sender or @domain, folder, n, in the inbox now)] strongest first.
    count {folder: {sender: n}} of what the profile put there itself; inbox {sender: n}."""
    total = {}
    for f, by in count.items():
        for a, n in by.items():
            total[a] = total.get(a, 0) + n
    out, done = [], set()
    # a domain only with a clear picture: several addresses, all of it in one folder, nothing in the inbox, no freemail
    doms = {}
    for f, by in count.items():
        for a, n in by.items():
            doms.setdefault(a.split("@")[-1], {}).setdefault(f, {})[a] = n
    for dom, fs in doms.items():
        addrs = {a for by in fs.values() for a in by}
        if dom in FREEMAIL or len(fs) != 1 or len(addrs) < 2 or any(a in own for a in addrs):
            continue
        f, by = next(iter(fs.items()))
        n = sum(by.values())
        if n >= SUGGEST_MIN and not any(a.split("@")[-1] == dom for a in inbox) and ("@" + dom, f) not in skip:
            out.append(("@" + dom, f, n, 0))
            done |= addrs
    for f, by in count.items():
        for a, n in by.items():
            if a in done or a in own or (a, f) in skip:
                continue
            if n >= SUGGEST_MIN and n >= SUGGEST_SHARE * (total[a] + inbox.get(a, 0)):
                out.append((a, f, n, inbox.get(a, 0)))
    return sorted(out, key=lambda x: -x[2])


def suggest(uid, now=None):
    """The night look of one profile: only the folders below its KI folder (Dominik 2026-10-21 09:55), only when one of
    them changed since the last look; what „Mails aufräumen“ moved itself (its log, by Message-ID) never counts.
    Senders with a rule (here or in „Mails aufräumen“) or on the never list are left out. Returns new suggestions.
    With Sortieren aus Korrekturen lernen: what either sorter moved counts only where the person put it since (FIX_WEIGHT times),
    the folder „Falsch sortiert“ never counts, and such a mail found elsewhere is a correction (correct)."""
    now = time.time() if now is None else now
    who = profiles.log_name(profiles.by_id(uid))
    st = tidy.state(uid)
    root, theirs = st["root"], {x["mid"] for x in st["log"] if x.get("mid")}
    d = load(uid)
    learn_on = features.allowed("maillearn", uid)
    ruled = {(r.get("account", ""), r["when"].get("from", "")) for r in d["rules"]}
    new, looked = [], dict(d["looked"])
    for acct in mail.get(uid)["accounts"]:
        aid = acct["id"]
        fixes, usual = [], {}
        try:
            with tidy.Box(acct) as box:
                wrong = ensure_wrong(uid, box, st) if learn_on else ""
                under = _under(box, root)
                mark = {n: _status(box, n) for n in under}
                if not under or looked.get(aid) == mark:
                    continue
                looked[aid] = mark
                moved = {m: _srv(box, x) for m, x in spark_moved(uid, aid, d, st).items() if not x.get("undone")} if learn_on else {}
                count, where = {}, {}
                for n in under:
                    got = _senders(box, n, tidy.LOG_DAYS)
                    for a, ms in got.items():
                        where.update({m: (n, a) for m in ms if m})
                    if n == wrong:
                        continue
                    if learn_on:   # the Spark's own moves count only when the person put the mail somewhere else since
                        by = {a: sum(1 if not m or m not in moved else 0 if moved[m] == n else FIX_WEIGHT for m in ms)
                              for a, ms in got.items()}
                    else:
                        by = {a: sum(1 for m in ms if not m or m not in theirs) for a, ms in got.items()}
                    count[n] = {a: k for a, k in by.items() if k}
                got = _senders(box, "INBOX", tidy.LOG_DAYS)
                inbox = {a: len(ms) for a, ms in got.items()}
                if learn_on:
                    for a, ms in got.items():
                        where.update({m: ("INBOX", a) for m in ms if m})
                    all_moved = spark_moved(uid, aid, d, st)
                    for m, von in moved.items():
                        n, a = where.get(m, ("", ""))
                        if n and n != von:
                            fixes.append(found(box, all_moved[m], a, "" if n == wrong else n))
                    for n, by in count.items():
                        for a, k in by.items():
                            usual.setdefault(a, {})[n] = k
        except (OSError, ValueError, imaplib.IMAP4.error) as e:
            print(f"mail: rule suggestions not looked ({type(e).__name__}) | {who}", flush=True)
            continue
        if fixes:
            correct(uid, aid, fixes, usual=usual)
            d = load(uid)
        own = {str(acct.get("user") or "").lower()}
        skip = {(x["from"], x["folder"]) for x in d["suggest"] if x["account"] == aid}
        skip |= {(k.split("|")[1], k.split("|", 2)[2]) for k in d["never"] if k.startswith(aid + "|")}
        for a, f, n, inb in _weigh(count, inbox, own, skip):
            if (aid, a) in ruled or (not a.startswith("@") and tidy.rule_for(st, a)) or (a.startswith("@") and any(r["match"] == a for r in st["rules"])):
                continue
            new.append({"id": secrets.token_hex(4), "account": aid, "from": a, "folder": f, "n": n, "inbox": inb, "t": int(now)})
    new = new[:SUGGEST_DAY]
    with _lock:
        d = load(uid)
        d["looked"] = looked
        kept = (_fresh(d["suggest"], now) + new)[-SUGGEST_MAX:]
        old = [x["id"] for x in d["suggest"] if x["id"] not in {y["id"] for y in kept}]
        d["suggest"] = kept
        _save(uid, d)
    _cards_done(uid, old, "abgelaufen")
    for x in new:   # a card „Regel-Vorschlag“ in the assistant and under Offen (vorgaenge.py), the same buttons as here
        _card(uid, x)
    if new:
        _count.bump("nacht", len(new))
    print(f"mail: rule suggestions | {len(new)} | {who}", flush=True)
    return new


# ---------------------------------------------------------------- Karten (vorgaenge.py, Dominik 2026-10-21 „ok“ 3a)
# Each night's suggestion is also a card „Regel-Vorschlag“ in today's assistant chat and under Offen, with the buttons
# of the page: „Regel anlegen und ablegen“ (only while some of its mails lie in the inbox), „Regel anlegen“, „Nicht
# mehr fragen“. The card runs the same add/apply/never as the page (its checks, its journal lines); taking a
# suggestion on the page (or its expiry after SUGGEST_KEEP days) closes the card. Sender and folder are text on the card.
CARD = "regel"
# Sortieren aus Korrekturen lernen (plan mail-lernen 5a): the same kind, no new one; a suggestion's "kind" says which card it is:
#   "fix"    a correction with a goal: „War in A, gehört nach B“ – „Regel ändern“ (the rule's folder becomes B),
#            „Nur Ausnahme“ (the sender stays an exception), „Nicht mehr fragen“; without a rule (Mails aufräumen) „Regel anlegen“
#   "wohin"  a mail in „Falsch sortiert“: the sender's usual folders, „Posteingang“, „Anderer Ordner …“ (the page), „Nur
#            diese Mail“ (no exception for the sender), „Absender als Ausnahme“, „Nicht mehr fragen“
#   "pause"  a rule paused after FIX_PAUSE corrections: „Wieder einschalten“, „Regel ansehen …“ (the page)
WAYS = {"wohin": "E-Mail → Posteingang", "pause": "E-Mail → Regeln"}


def _rule_words(r):
    w = r.get("when") or {}
    return w.get("from") or (f"Betreff „{w['subject']}“" if w.get("subject") else w.get("to") or "…")


def _card(uid, x, say=True):
    import vorgaenge
    kind = x.get("kind", "")
    daten = {"weg": WAYS[kind]} if kind in WAYS else None
    if kind == "fix":
        titel = f"Regel-Vorschlag: Mails von {x['from']}"
        zeile = (f"War in „{x['von']}“, du hast sie nach „{x['folder']}“ gelegt. "
                 + ("Soll die Regel künftig dorthin sortieren?" if x.get("rid") else "Soll das künftig eine Regel machen?"))
    elif kind == "wohin":
        titel = "Wohin gehört diese Mail?"
        zeile = f"Von {x['from']}, der Spark hatte sie in „{x['von']}“ sortiert; du hast sie nach „Falsch sortiert“ gelegt."
    elif kind == "pause":
        r = next((y for y in load(uid)["rules"] if y["id"] == x.get("rid")), None)
        titel = f"Regel pausiert: {_rule_words(r) if r else '…'}"
        zeile = (f"Du hast in {FIX_DAYS} Tagen {x['n']} ihrer Mails umsortiert. Ändern, löschen oder wieder einschalten? "
                 "E-Mail → Regeln")
    else:
        titel = f"Regel-Vorschlag: Mails von {x['from']}"
        zeile = (f"legst du in „{x['folder']}“ ({x['n']}×)" + (f", {x['inbox']} liegen gerade im Posteingang" if x["inbox"] else "")
                 + ". Soll das künftig eine Regel machen?")
    vorgaenge.put(uid, CARD, f"{CARD}:{x['id']}", titel, zeile, daten=daten, say=say)


def _cards_done(uid, ids, wie):
    if not ids:
        return
    import vorgaenge
    for sid in ids:
        vorgaenge.done(uid, f"{CARD}:{sid}", wie)


def _card_sug(uid, x):
    return next((y for y in load(uid)["suggest"] if f"{CARD}:{y['id']}" == x["key"]), None)


def _rule_of(uid, sug):
    return next((r for r in load(uid)["rules"] if sug.get("rid") and r["id"] == sug["rid"]), None)


def _card_acts(uid, x):
    """The buttons the rules allow now: none without Mails ordnen (or, for a correction's card, without Aus Korrekturen
    lernen) or once the suggestion is gone."""
    sug = _card_sug(uid, x)
    if not sug or not features.allowed("mailmanage", uid):
        return set()
    kind = sug.get("kind", "")
    if kind and not features.allowed("maillearn", uid):
        return set()
    rule = _rule_of(uid, sug)
    if kind == "fix":
        return ({"rg_aendern", "rg_ausnahme"} if rule else {"rg_regel"}) | {"rg_nie"}
    if kind == "wohin":
        return {f"rg_w{i + 1}" for i in range(min(len(sug.get("ziele") or []), WOHIN_MAX))} | \
            {"rg_eingang", "oeffnen", "rg_nur", "rg_ausnahme", "rg_nie"}
    if kind == "pause":
        return {"oeffnen"} | ({"rg_an"} if rule and rule.get("on") is False else set())
    return {"rg_regel", "rg_nie"} | ({"rg_ablegen"} if sug["inbox"] else set())


def _card_names(uid, x):
    """The words of buttons that say what they do on this card (the folder of „Wohin …?“), shown as text."""
    sug = _card_sug(uid, x) or {}
    if sug.get("kind") == "wohin":
        out = {f"rg_w{i + 1}": (f"Nach „{f[:40]}“", f'To "{f[:40]}"') for i, f in enumerate((sug.get("ziele") or [])[:WOHIN_MAX])}
        return dict(out, rg_ausnahme=("Absender als Ausnahme", "Sender as exception"), oeffnen=("Anderer Ordner …", "Other folder …"))
    if sug.get("kind") == "pause":
        return {"oeffnen": ("Regel ansehen …", "Show the rule …")}
    return {}


def _drop(uid, sid, wie):
    with _lock:
        d = load(uid)
        d["suggest"] = [y for y in d["suggest"] if y["id"] != sid]
        _save(uid, d)
    _cards_done(uid, [sid], wie)


def _set_except(uid, rid, sender, on):
    """The sender onto the rule's exceptions (on) or off them again; True when the rule is there."""
    with _lock:
        d = load(uid)
        r = next((y for y in d["rules"] if y["id"] == rid), None)
        if r is None:
            return False
        exc = [a for a in (r.get("except") or []) if a != sender]
        r["except"] = (exc + [sender])[-EXCEPT_MAX:] if on else exc
        _save(uid, d)
    return True


def _card_run(uid, x, name):
    """A button of the card: the page's own add/apply/never, or for a correction's card its own small step (each with
    its journal line); the card closes through _cards_done."""
    import vorgaenge
    if name not in vorgaenge.ARTEN[CARD]["acts"] or name == "oeffnen":
        return None
    sug = _card_sug(uid, x)
    who = profiles.log_name(profiles.by_id(uid))
    if not sug:
        print(f"mail: rule card {name} refused, not found | {who}", flush=True)
        raise vorgaenge.HTTPException(404, "Diesen Vorschlag gibt es nicht mehr.")
    body = {"account": sug["account"], "from": sug["from"], "folder": sug["folder"]}
    try:
        if sug.get("kind"):
            return _fix_run(uid, sug, name, who)
        if name == "rg_nie":
            never(uid, body)
            return {"text": "Gut, dazu frage ich nicht mehr."}
        r = add(uid, {"account": sug["account"], "when": {"from": sug["from"]}, "then": {"folder": sug["folder"]}})
        print(f"mail: rule suggestion taken | card | {who}", flush=True)
        if name == "rg_ablegen":
            n = apply(uid, r["id"])["n"]
            return {"text": f"Regel angelegt, {n} Mails aus dem Posteingang abgelegt."}
        return {"text": "Regel angelegt: neue Mails kommen künftig gleich in den Ordner."}
    except notaus.NotausAktiv:
        print(f"mail: rule card {name} refused, notaus | {who}", flush=True)
        raise vorgaenge.HTTPException(503, "Notaus: gerade wird nichts geändert.")
    except LookupError as e:
        print(f"mail: rule card {name} refused, not found | {who}", flush=True)
        raise vorgaenge.HTTPException(404, str(e)[:200])
    except (ValueError, OSError, imaplib.IMAP4.error) as e:
        print(f"mail: rule card {name} failed ({type(e).__name__}) | {who}", flush=True)
        raise vorgaenge.HTTPException(400, str(e)[:200] if isinstance(e, ValueError) else "Das Postfach war nicht erreichbar.")


def _fix_run(uid, sug, name, who):
    """The buttons of a correction's card (Sortieren aus Korrekturen lernen); the panel's fixed steps, never the model."""
    aid, sender, rid = sug["account"], sug.get("from", ""), sug.get("rid", "")
    if name == "rg_nie":
        if sug["kind"] == "fix":
            never(uid, {"account": aid, "from": sender, "folder": sug["folder"]})
        else:
            with _lock:
                d = load(uid)
                k = _key(aid, sender, "")
                d["never"] = [y for y in d["never"] if y != k][-(LEARN_MAX - 1):] + [k]
                _save(uid, d)
            print(f"mail: rule hint never | {who}", flush=True)
        _drop(uid, sug["id"], "ausblenden")
        return {"text": "Gut, dazu frage ich nicht mehr."}
    if name == "rg_aendern":
        rule = _rule_of(uid, sug)
        if not rule:
            raise LookupError("Diese Regel gibt es nicht mehr.")
        add(uid, {"account": rule.get("account", ""), "when": rule["when"], "then": dict(rule["then"], folder=sug["folder"]),
                  "on": True}, rid)
        _set_except(uid, rid, sender, False)     # the rule now sorts this sender right
        print(f"mail: rule changed | card | {who}", flush=True)
        _drop(uid, sug["id"], "erledigt")
        return {"text": f"Regel geändert: Mails kommen künftig nach „{sug['folder']}“."}
    if name == "rg_an":
        rule = _rule_of(uid, sug)
        if not rule:
            raise LookupError("Diese Regel gibt es nicht mehr.")
        add(uid, {"account": rule.get("account", ""), "when": rule["when"], "then": rule["then"], "on": True}, rid)
        print(f"mail: rule resumed | card | {who}", flush=True)
        _drop(uid, sug["id"], "erledigt")
        return {"text": "Die Regel ist wieder an."}
    if name in ("rg_ausnahme", "rg_nur"):
        if rid and _set_except(uid, rid, sender, name == "rg_ausnahme"):
            pass
        elif name == "rg_ausnahme" and sender:      # „Mails aufräumen“ sorted it: the sender stays in the inbox there
            tidy._mut(uid, lambda d: tidy.add_rule(d, sender, "keep"))
        print(f"mail: rule exception | card {'kept' if name == 'rg_ausnahme' else 'removed'} | {who}", flush=True)
        _drop(uid, sug["id"], "erledigt")
        return {"text": "Der Absender bleibt eine Ausnahme dieser Regel." if name == "rg_ausnahme"
                else "Gut, nur diese Mail; für den Absender ändert sich nichts."}
    if name == "rg_eingang" or name.startswith("rg_w"):
        ziele = sug.get("ziele") or []
        i = int(name[-1]) - 1 if name.startswith("rg_w") else -1
        if i >= len(ziele):
            raise LookupError("Diesen Ordner gibt es auf der Karte nicht mehr.")
        dst = ziele[i] if i >= 0 else "INBOX"
        _place(uid, aid, sug["mid"], dst)       # its line: mail: rule card place; refused or failed: _card_run
        _drop(uid, sug["id"], "erledigt")
        correct(uid, aid, [{"mid": sug["mid"], "by": "rule" if rid else "tidy", "rid": rid, "von": sug.get("von", ""),
                            "from": sender, "nach": dst}])
        return {"text": "In den Posteingang gelegt." if dst == "INBOX" else f"Abgelegt in „{dst}“."}
    raise ValueError("Diesen Knopf gibt es so nicht.")


def _register():
    import vorgaenge
    vorgaenge.ARTEN[CARD] = {"de": "Regel-Vorschlag", "en": "Rule suggestion", "sym": "mail", "mail": True, "dringend": False,
                             "acts": ("rg_ablegen", "rg_regel", "rg_aendern", "rg_w1", "rg_w2", "rg_w3", "rg_eingang", "oeffnen",
                                      "rg_nur", "rg_ausnahme", "rg_an", "rg_nie")}
    vorgaenge.AKTIONEN.update(rg_ablegen={"de": "Regel anlegen und ablegen", "en": "Make the rule and file them", "stufe": "direkt"},
                              rg_regel={"de": "Regel anlegen", "en": "Make the rule", "stufe": "direkt"},
                              rg_nie={"de": "Nicht mehr fragen", "en": "Don't ask again", "stufe": "direkt"},
                              rg_aendern={"de": "Regel ändern", "en": "Change the rule", "stufe": "direkt"},
                              rg_ausnahme={"de": "Nur Ausnahme", "en": "Exception only", "stufe": "direkt"},
                              rg_nur={"de": "Nur diese Mail", "en": "Just this mail", "stufe": "direkt"},
                              rg_w1={"de": "Ordner 1", "en": "Folder 1", "stufe": "direkt"},
                              rg_w2={"de": "Ordner 2", "en": "Folder 2", "stufe": "direkt"},
                              rg_w3={"de": "Ordner 3", "en": "Folder 3", "stufe": "direkt"},
                              rg_eingang={"de": "Posteingang", "en": "Inbox", "stufe": "direkt"},
                              rg_an={"de": "Wieder einschalten", "en": "Switch on again", "stufe": "direkt"})
    vorgaenge.QUELLEN[CARD] = {"acts": _card_acts, "run": _card_run, "names": _card_names}
    vorgaenge.OFFEN_STUNDEN[CARD] = SUGGEST_KEEP * 24


def _night(now):
    import datetime
    return SUGGEST_NIGHT[0] <= datetime.datetime.fromtimestamp(now).hour < SUGGEST_NIGHT[1]


async def due_once(now=None):
    """Called each minute (panel.py): profiles with rules whose look is due; never during a Notaus. At night one
    profile per minute gets its look for rule suggestions (once a night)."""
    import asyncio
    now = time.time() if now is None else now
    c = features.chat_cfg()
    if _night(now):
        day = time.strftime("%Y-%m-%d", time.localtime(now))
        for uid in profiles.user_ids():
            if _sug_day.get(uid) == day or not mail.get(uid)["accounts"]:
                continue
            if not features.allowed("mailmanage", uid, c) or notaus.blocks("auto", uid):
                continue
            _sug_day[uid] = day
            try:
                await asyncio.to_thread(suggest, uid, now)
            except Exception as e:
                print(f"mail: rule suggestions failed ({type(e).__name__}) | {profiles.log_name(profiles.by_id(uid))}", flush=True)
            break
    for uid in profiles.user_ids():
        if now - _last.get(uid, 0) < RUN_EVERY - 5 or not os.path.exists(_file(uid)):
            continue
        if not features.allowed("mailmanage", uid, c) or notaus.blocks("auto", uid):
            continue
        _last[uid] = now
        try:
            await asyncio.to_thread(run, uid, now)
        except notaus.NotausAktiv:
            print(f"mail: rules not run, notaus | {profiles.log_name(profiles.by_id(uid))}", flush=True)


def _matching(uid, rule, most):
    """{account id: [uid, …]} of inbox mails of the last PREVIEW_DAYS the rule fits (newest PREVIEW_MAX looked at);
    a mail the Spark moved and the person put back is never one of them (user_moved)."""
    out, d, st = {}, load(uid), tidy.state(uid)
    for acct in mail.get(uid)["accounts"]:
        if rule.get("account") and rule["account"] != acct["id"]:
            continue
        moved = spark_moved(uid, acct["id"], d, st)
        with tidy.Box(acct) as box:
            box.select("INBOX")
            uids = sorted(box.search("SINCE", tidy._since(PREVIEW_DAYS)))[-PREVIEW_MAX:]
            heads = {u: head(m) for u, m in box.headers(uids, HEAD).items()}
            hit = [u for u in uids if u in heads and fits(rule, heads[u]) and not user_moved(moved, heads[u]["mid"], "INBOX")]
            if hit:
                out[acct["id"]] = hit[-most:]
    return out


def preview(uid, body):
    """Probelauf: how many inbox mails of the last PREVIEW_DAYS a rule (not saved yet) fits. Nothing changes."""
    rule = clean(uid, body)
    hits = _matching(uid, rule, PREVIEW_MAX)
    n = sum(len(v) for v in hits.values())
    print(f"mail: rule preview | {n} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return {"n": n, "days": PREVIEW_DAYS}


def apply(uid, rid):
    """„Auch die vorhandenen“: the saved rule on the inbox mails it fits now (at most APPLY_MAX).
    {"n": how many, "moved": [{"acct", "mids"}], "folder"} for „Rückgängig“ (postfach.back_many)."""
    import postfach
    who = profiles.log_name(profiles.by_id(uid))
    try:
        notaus.stop("aktion", uid)
        rule = next((r for r in load(uid)["rules"] if r["id"] == rid), None)
        if not rule:
            raise LookupError("no such rule")
        n, moved = 0, []
        for aid, us in _matching(uid, rule, APPLY_MAX).items():
            acct = next(a for a in mail.get(uid)["accounts"] if a["id"] == aid)
            with tidy.Box(acct) as box:
                targets, _ = postfach._targets(box)
                box.select("INBOX", write=True)
                mids = _do(box, targets, rule, us)
            _remember(uid, aid, rule, mids)
            n += len(us)
            if mids:
                moved.append({"acct": aid, "mids": mids[:postfach.MANY]})
        if n:
            _bump(uid, rid, n)
            mail.changed(uid, "", "back")
    except notaus.NotausAktiv:
        print(f"mail: rule apply refused, notaus | {who}", flush=True)
        raise
    except LookupError:
        print(f"mail: rule apply refused, not found | {who}", flush=True)
        raise
    except Exception as e:
        print(f"mail: rule apply failed ({type(e).__name__}) | {who}", flush=True)
        raise
    print(f"mail: rule apply done | {n} | {who}", flush=True)
    return {"n": n, "moved": moved, "folder": rule["then"].get("folder", "")}


# ---------------------------------------------------------------- Mail-Statistik (Dominik 2026-10-21 „6“)
# Who writes most in the last mail.DAYS days and how many mails came each week, to tidy up: from the listing the
# Mail-Vorrat keeps anyway (mailvorrat.HEADS a mailbox), so nothing is read again while it is fresh. Per sender the
# number, the unread ones and whether a rule (here or in Mails aufräumen) already takes it; the page offers
# „Regel …“ from there. Counted by the panel, nothing goes to the model.
STATS_TOP = 15
STATS_WEEKS = 4
STATS_BUDGET = 5


def stats(uid, now=None):
    """{"weeks": [n, …] newest first, "senders": [{addr, name, n, unread, rule}], "total", "unread", "as_of"};
    TimeoutError while a first reading still goes on."""
    import mailvorrat
    now = time.time() if now is None else now
    who = profiles.log_name(profiles.by_id(uid))
    accts = mail.get(uid)["accounts"]
    try:
        (found, _, _), as_of = mail.lookup(uid, "", mail.DAYS, False, mailvorrat.HEADS * max(1, len(accts)),
                                           stale=True, budget=STATS_BUDGET)
    except TimeoutError:
        print(f"mail: stats too slow | {who}", flush=True)
        raise
    d, st = load(uid), tidy.state(uid)
    weeks, people, unread = [0] * STATS_WEEKS, {}, 0
    for aid, _, h in found:
        addr = (_addrs(h.get("from", "")) or [""])[0]
        if not addr:
            continue
        age = int((now - h["date"].timestamp()) // (7 * 86400))
        if 0 <= age < STATS_WEEKS:
            weeks[age] += 1
        x = people.setdefault(addr, {"addr": addr, "name": "", "n": 0, "unread": 0, "rule": False, "acct": aid})
        x["n"] += 1
        x["unread"] += 1 if h.get("unread") else 0
        unread += 1 if h.get("unread") else 0
        name = email.utils.parseaddr(h.get("from", ""))[0]
        x["name"] = x["name"] or re.sub(r"[\x00-\x1f]", "", name)[:60]
    top = sorted(people.values(), key=lambda x: (-x["n"], x["addr"]))[:STATS_TOP]
    for x in top:
        h = {"from": x["addr"], "to": [], "subject": "", "attach": False}
        x["rule"] = bool(first(d["rules"], h, x["acct"]) or tidy.rule_for(st, x["addr"]))
    _count.bump("statistik")
    print(f"mail: stats shown | {len(found)} mails, {len(people)} senders | {who}", flush=True)
    return {"weeks": weeks, "senders": top, "total": len(found), "unread": unread, "as_of": int(as_of or now)}


def for_live():
    """Live (Post): profiles with rules, rules in all, mails the rules took today, mails put back that a rule leaves
    alone now, corrections today, exceptions and rules paused by corrections; numbers only."""
    c = _count.counts()
    profs = rules = exc = paused = 0
    for uid in profiles.user_ids():
        if os.path.exists(_file(uid)):
            rs = load(uid)["rules"]
            profs += 1 if rs else 0
            rules += len(rs)
            exc += sum(len(r.get("except") or []) for r in rs)
            paused += sum(1 for r in rs if r.get("paused") and r.get("on") is False)
    return {"profiles": profs, "rules": rules, "taken": c.get("genommen", 0), "back": c.get("zurueck", 0), "hints": c.get("vorschlaege", 0),
            "night": c.get("nacht", 0), "stats": c.get("statistik", 0),
            # Sortieren aus Korrekturen lernen: on, corrections today, exceptions and paused rules in all (numbers only)
            "learn": features.admin_on("maillearn"), "fixes": c.get("korrektur", 0), "excepts": exc, "paused": paused}


_register()
