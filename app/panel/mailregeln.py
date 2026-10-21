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
FREEMAIL = ("gmail.com", "googlemail.com", "gmx.de", "gmx.net", "gmx.at", "gmx.ch", "web.de", "t-online.de", "icloud.com",
            "me.com", "mac.com", "outlook.com", "outlook.de", "hotmail.com", "hotmail.de", "live.com", "live.de", "yahoo.com",
            "yahoo.de", "aol.com", "freenet.de", "posteo.de", "mailbox.org", "proton.me", "protonmail.com", "online.de")
_lock = threading.Lock()
_last = {}               # uid -> when its rules last ran
_sug_day = {}            # uid -> the night its rule suggestions were looked for
_count = DayCounter(genommen=0, laeufe=0, vorschlaege=0, nacht=0, statistik=0)   # per day: mails taken, looks, rule hints, night suggestions, statistics shown


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
        gone = [x["id"] for x in d["suggest"] if x["account"] == r["account"] and x["from"] == r["when"]["from"]]
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
    sug = [{k: x[k] for k in ("id", "account", "from", "folder", "n", "inbox")} | {"box": names.get(x["account"], "")}
           for x in _fresh(d["suggest"]) if x["account"] in names]
    return {"rules": rules, "tidy": old, "accounts": [{"id": k, "name": v} for k, v in names.items()], "suggest": sug}


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
    Senders with a rule (here or in „Mails aufräumen“) or on the never list are left out. Returns new suggestions."""
    now = time.time() if now is None else now
    who = profiles.log_name(profiles.by_id(uid))
    st = tidy.state(uid)
    root, theirs = st["root"], {x["mid"] for x in st["log"] if x.get("mid")}
    d = load(uid)
    ruled = {(r.get("account", ""), r["when"].get("from", "")) for r in d["rules"]}
    new, looked = [], dict(d["looked"])
    for acct in mail.get(uid)["accounts"]:
        aid = acct["id"]
        try:
            with tidy.Box(acct) as box:
                under = _under(box, root)
                mark = {n: _status(box, n) for n in under}
                if not under or looked.get(aid) == mark:
                    continue
                looked[aid] = mark
                count = {}
                for n in under:
                    by = {a: sum(1 for m in ms if not m or m not in theirs) for a, ms in _senders(box, n, tidy.LOG_DAYS).items()}
                    count[n] = {a: k for a, k in by.items() if k}
                inbox = {a: len(ms) for a, ms in _senders(box, "INBOX", tidy.LOG_DAYS).items()}
        except (OSError, ValueError, imaplib.IMAP4.error) as e:
            print(f"mail: rule suggestions not looked ({type(e).__name__}) | {who}", flush=True)
            continue
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


def _card(uid, x):
    import vorgaenge
    titel = f"Regel-Vorschlag: Mails von {x['from']}"
    zeile = (f"legst du in „{x['folder']}“ ({x['n']}×)" + (f", {x['inbox']} liegen gerade im Posteingang" if x["inbox"] else "")
             + ". Soll das künftig eine Regel machen?")
    vorgaenge.put(uid, CARD, f"{CARD}:{x['id']}", titel, zeile, say=True)


def _cards_done(uid, ids, wie):
    if not ids:
        return
    import vorgaenge
    for sid in ids:
        vorgaenge.done(uid, f"{CARD}:{sid}", wie)


def _card_sug(uid, x):
    return next((y for y in load(uid)["suggest"] if f"{CARD}:{y['id']}" == x["key"]), None)


def _card_acts(uid, x):
    """The buttons the rules allow now: none without Mails ordnen or once the suggestion is gone."""
    sug = _card_sug(uid, x)
    if not sug or not features.allowed("mailmanage", uid):
        return set()
    return {"rg_regel", "rg_nie"} | ({"rg_ablegen"} if sug["inbox"] else set())


def _card_run(uid, x, name):
    """A button of the card: the page's own add/apply/never; the card closes through _cards_done."""
    import vorgaenge
    if name not in ("rg_regel", "rg_ablegen", "rg_nie"):
        return None
    sug = _card_sug(uid, x)
    if not sug:
        raise vorgaenge.HTTPException(404, "Diesen Vorschlag gibt es nicht mehr.")
    body = {"account": sug["account"], "from": sug["from"], "folder": sug["folder"]}
    try:
        if name == "rg_nie":
            never(uid, body)
            return {"text": "Gut, dazu frage ich nicht mehr."}
        r = add(uid, {"account": sug["account"], "when": {"from": sug["from"]}, "then": {"folder": sug["folder"]}})
        print(f"mail: rule suggestion taken | card | {profiles.log_name(profiles.by_id(uid))}", flush=True)
        if name == "rg_ablegen":
            n = apply(uid, r["id"])["n"]
            return {"text": f"Regel angelegt, {n} Mails aus dem Posteingang abgelegt."}
        return {"text": "Regel angelegt: neue Mails kommen künftig gleich in den Ordner."}
    except (ValueError, LookupError) as e:
        raise vorgaenge.HTTPException(400, str(e)[:200])


def _register():
    import vorgaenge
    vorgaenge.ARTEN[CARD] = {"de": "Regel-Vorschlag", "en": "Rule suggestion", "sym": "mail", "mail": True, "dringend": False,
                             "acts": ("rg_ablegen", "rg_regel", "rg_nie")}
    vorgaenge.AKTIONEN.update(rg_ablegen={"de": "Regel anlegen und ablegen", "en": "Make the rule and file them", "stufe": "direkt"},
                              rg_regel={"de": "Regel anlegen", "en": "Make the rule", "stufe": "direkt"},
                              rg_nie={"de": "Nicht mehr fragen", "en": "Don't ask again", "stufe": "direkt"})
    vorgaenge.QUELLEN[CARD] = {"acts": _card_acts, "run": _card_run}
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
    """Live (Post): profiles with rules, rules in all, mails the rules took today; numbers only."""
    c = _count.counts()
    profs = rules = 0
    for uid in profiles.user_ids():
        if os.path.exists(_file(uid)):
            n = len(load(uid)["rules"])
            profs += 1 if n else 0
            rules += n
    return {"profiles": profs, "rules": rules, "taken": c.get("genommen", 0), "hints": c.get("vorschlaege", 0),
            "night": c.get("nacht", 0), "stats": c.get("statistik", 0)}


_register()
