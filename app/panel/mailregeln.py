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
_lock = threading.Lock()
_last = {}               # uid -> when its rules last ran
_count = DayCounter(genommen=0, laeufe=0, vorschlaege=0)   # per day: mails the rules took, looks, rule hints


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
            r = old
        else:
            if len(d["rules"]) >= MAX_RULES:
                raise ValueError(f"at most {MAX_RULES} rules")
            r.update(id=secrets.token_hex(4), made=int(time.time()), n={})
            d["rules"].append(r)
        _save(uid, d)
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


def learn(uid, account_id, senders, folder, now=None):
    """Counts the page's moves of these senders into `folder`; {"account", "from", "folder", "n"} for the hint when
    one sender reached LEARN_AFTER moves within LEARN_DAYS (and is then counted from zero again), else None."""
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
            n = (learnt.get(k) or [0, now])[0] + 1
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
        _save(uid, d)
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
        _save(uid, d)
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
    return {"rules": rules, "tidy": old, "accounts": [{"id": k, "name": v} for k, v in names.items()]}


# ---------------------------------------------------------------- deciding
def _addrs(v):
    return [a.lower() for _, a in email.utils.getaddresses([str(v or "")]) if a]


def fits(rule, h):
    """Does the rule fit a message's header h ({from, to: [..], subject, attach})? Words compared, never run."""
    w = rule["when"]
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
    for acct in mail.get(uid)["accounts"]:
        mine = [r for r in rules if not r.get("account") or r["account"] == acct["id"]]
        if not mine:
            continue
        try:
            with tidy.Box(acct) as box:
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
                todo = {}
                for u in new:
                    if u in heads:
                        r = first(mine, head(heads[u]), acct["id"])
                        if r:
                            todo.setdefault(r["id"], (r, []))[1].append(u)
                for r, us in todo.values():
                    try:
                        _do(box, targets, r, us)
                        _bump(uid, r["id"], len(us))
                        taken += len(us)
                    except (ValueError, OSError) as e:
                        errors += 1
                        print(f"mail: rule failed ({type(e).__name__}) | {profiles.log_name(profiles.by_id(uid))}", flush=True)
                seen[acct["id"]] = {"v": v, "uid": new[-1]}
        except (OSError, ValueError, imaplib.IMAP4.error) as e:
            errors += 1
            print(f"mail: rules not run ({type(e).__name__}) | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    with _lock:
        d = load(uid)
        d["seen"] = seen
        _save(uid, d)
    _count.bump("laeufe")
    print(f"mail: rules run | {taken} taken, {errors} errors | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    if taken:
        mail.changed(uid, "", "back")   # the cached inbox listing is fetched anew
    return {"taken": taken, "errors": errors}


async def due_once(now=None):
    """Called each minute (panel.py): profiles with rules whose look is due; never during a Notaus."""
    import asyncio
    now = time.time() if now is None else now
    c = features.chat_cfg()
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
    """{account id: [uid, …]} of inbox mails of the last PREVIEW_DAYS the rule fits (newest PREVIEW_MAX looked at)."""
    out = {}
    for acct in mail.get(uid)["accounts"]:
        if rule.get("account") and rule["account"] != acct["id"]:
            continue
        with tidy.Box(acct) as box:
            box.select("INBOX")
            uids = sorted(box.search("SINCE", tidy._since(PREVIEW_DAYS)))[-PREVIEW_MAX:]
            heads = box.headers(uids, HEAD)
            hit = [u for u in uids if u in heads and fits(rule, head(heads[u]))]
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


def for_live():
    """Live (Post): profiles with rules, rules in all, mails the rules took today; numbers only."""
    c = _count.counts()
    profs = rules = 0
    for uid in profiles.user_ids():
        if os.path.exists(_file(uid)):
            n = len(load(uid)["rules"])
            profs += 1 if n else 0
            rules += n
    return {"profiles": profs, "rules": rules, "taken": c.get("genommen", 0), "hints": c.get("vorschlaege", 0)}
