"""Mails senden auf der Seite E-Mail (plan kalender-mail Stufe 3, function "Mails senden", chat.mail_send, off):
a profile writes a new mail or answers one of its inbox, sees the finished mail on a preview sheet and only its
„Senden“ there sends it. Two steps, both from the own browser login:

  - preview(): checks every field with fixed rules and keeps the finished mail for PREVIEW_SECONDS under a random
    token, bound to the profile; the sheet shows exactly what will go out (from, to, copy, subject, text)
  - send(): that token, once; the mail goes from the mailbox's own outgoing server (SMTP over TLS, port 465 or
    STARTTLS required on 587, netguard.USER), with the same login as reading, and a copy lands in its sent folder
    where the server does not keep one itself

Senden per Sprache (stage 3b, chat.mail_send_voice "off" | "answers" | "all", default "off"): no tool for the model.
The panel's fixed rules (answer) take the person's own words: "Antworte ihr per Mail: …" right after the assistant
read a mail (to its sender, From only, never Reply-To), and with "all" also "Schreib eine Mail an Anna: …" (Anna
only from the own contacts with exactly one address, or an address said in full). The panel reads recipient and text
back and sends only after the person's plain "Ja" in the next message, on the same device (Freigabe-Karte, ablauf
kind "senden"); never for guests, another voice or Telegram without the private release.

Never more than MAX_TO recipients, MAX_DAY mails a day per profile, no HTML, no header from the form (line breaks in a
field are refused), no attachment except those of a forwarded mail. An answer takes recipient, subject ("Re: …") and
In-Reply-To/References from the original in the own inbox. Weiterleiten (Mailclient Stufe C): the own words, then the
original's sender, date, subject and text below a fixed line, with its attachments if wanted (together at most
FORWARD_FILES), subject "Fwd: …"; the recipients are typed like for a new mail. The Notaus holds sending off. Logs carry fixed words, numbers and the profile's log
name only, never an address, a subject or the text.
"""
import email.message
import email.policy
import email.utils
import imaplib
import os
import re
import smtplib
import ssl
import threading
import time

import features
import mail
from common import STATE, read_json, write_json
import netguard
import notaus
import profiles
import tidy

MAX_TO = 10
MAX_DAY = 30
MAX_SUBJECT = 200
MAX_TEXT = 20000
FORWARD_FILES = 20 * 1024 * 1024   # the attachments of a forwarded mail together
PREVIEW_SECONDS = 600
TIMEOUT = 30
# the outgoing server of the known providers (host of the incoming one → host, port); 465 = TLS, 587 = STARTTLS
SMTP_FOR = {"imap.mail.me.com": ("smtp.mail.me.com", 587), "imap.gmail.com": ("smtp.gmail.com", 465),
            "imap.gmx.net": ("mail.gmx.net", 465), "imap.web.de": ("smtp.web.de", 587)}
KEEPS_SENT = {"smtp.mail.me.com", "smtp.gmail.com"}   # these put the sent mail into "Gesendet" themselves
ADDR = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                  r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+")
SMTP = netguard.SMTP           # checked address (netguard.USER); tests replace both with a fake server
SMTP_SSL = netguard.SMTP_SSL
_lock = threading.Lock()
_pending = {}                  # token → {"uid", "acct", "msg", "n", "t"}
_today = {"day": "", "n": {}}  # mails sent today per profile (MAX_DAY) and for Live (a number, never which)
# the day's count survives a restart of the panel (V01.0.825, code check 19.10. C3: before, every restart allowed
# MAX_DAY mails more); only numbers per profile id
SENT_FILE = os.path.join(STATE, "mail-gesendet.json")


def outgoing(acct):
    """(host, port) of the mailbox's outgoing server."""
    if acct.get("smtp_host"):
        return acct["smtp_host"], int(acct.get("smtp_port") or 465)
    host = acct["host"]
    if host in SMTP_FOR:
        return SMTP_FOR[host]
    return ("smtp." + host[5:] if host.startswith("imap.") else host), 465


def _addrs(raw, label):
    """The addresses of a form field ("a@x.de, Anna <b@y.de>"), each checked; ValueError otherwise."""
    raw = str(raw or "")
    if re.search(r"[\r\n]", raw):
        raise ValueError(f"{label}: no line breaks")
    out = []
    for name, addr in email.utils.getaddresses([raw[:2000]]):
        addr = addr.strip()
        if not addr and not name.strip():
            continue
        if not ADDR.fullmatch(addr):
            raise ValueError(f"{label}: not an e-mail address")
        out.append(email.utils.formataddr((name.strip()[:80], addr)) if name.strip() else addr)
    return out


def _count(uid):
    day = time.strftime("%Y-%m-%d")
    if _today["day"] != day:
        kept = read_json(SENT_FILE, {})
        kept = kept if isinstance(kept, dict) and kept.get("day") == day and isinstance(kept.get("n"), dict) else {}
        _today.update(day=day, n={str(k): int(v) for k, v in (kept.get("n") or {}).items()
                                  if isinstance(v, int) and 0 < v <= 10 * MAX_DAY})
    return _today["n"].get(uid, 0)


def today():
    """Live: how many mails were sent from the page today, all profiles together."""
    return sum(_today["n"].values()) if _today["day"] == time.strftime("%Y-%m-%d") else 0


def preview(uid, body):
    """The finished mail of the form for the preview sheet, and its token; ValueError for anything not allowed,
    LookupError when the mail to answer is no longer there."""
    who = profiles.log_name(profiles.by_id(uid))
    try:
        out = _preview(uid, body if isinstance(body, dict) else {})
    except LookupError:
        print(f"mail: send preview refused, not found | {who}", flush=True)
        raise
    except ValueError:
        print(f"mail: send preview refused | {who}", flush=True)
        raise
    print(f"mail: send preview | {out['n']} recipients | {who}", flush=True)
    return out


def _preview(uid, body):
    if _count(uid) >= MAX_DAY:
        raise ValueError(f"at most {MAX_DAY} mails a day")
    ref = str(body.get("reply") or "").strip()[:40]
    fwd = "" if ref else str(body.get("forward") or "").strip()[:40]
    acct_id = str(body.get("account") or "").strip()[:20]
    if ref or fwd:
        acct_id = (ref or fwd).split(":")[0]
    accts = mail.get(uid)["accounts"]
    # no mailbox named (the iPhone app, a new mail): the first one
    acct = next((a for a in accts if a["id"] == acct_id), None) if acct_id else (accts[0] if accts else None)
    if not acct:
        raise ValueError("unknown mailbox")
    if not ADDR.fullmatch(acct["user"]):
        raise ValueError("this mailbox's user name is not an e-mail address, so it cannot send")
    to, cc = _addrs(body.get("to"), "To"), _addrs(body.get("cc"), "Copy")
    if not to:
        raise ValueError("To: at least one address")
    if len(to) + len(cc) > MAX_TO:
        raise ValueError(f"at most {MAX_TO} recipients")
    subject = str(body.get("subject") or "").strip()
    if re.search(r"[\r\n]", subject) or len(subject) > MAX_SUBJECT:
        raise ValueError(f"Subject: one line, at most {MAX_SUBJECT} characters")
    text = str(body.get("text") or "").replace("\r\n", "\n").strip()
    if not text and not fwd:
        raise ValueError("the mail has no text")
    if len(text) > MAX_TEXT:
        raise ValueError(f"at most {MAX_TEXT} characters of text")
    msg = email.message.EmailMessage(policy=email.policy.SMTP)
    prof = profiles.by_id(uid) or {}
    msg["From"] = email.utils.formataddr((str(prof.get("name") or "")[:80], acct["user"])) if prof.get("name") else acct["user"]
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    if ref:
        orig = mail.message(uid, ref)
        if orig is None:
            raise LookupError("the mail to answer is not there")
        mid = str(orig.get("Message-ID") or "").strip()
        if re.fullmatch(r"<[^<>\s]{1,250}>", mid):
            msg["In-Reply-To"] = mid
            refs = " ".join(str(orig.get("References") or "").split()[-10:] + [mid])
            msg["References"] = refs[-990:]
        if not subject:
            old = mail._hdr(orig.get("Subject", ""))[:MAX_SUBJECT - 4]
            subject = old if re.match(r"(?i)(re|aw|antw)\s*:", old) else "Re: " + old
    attached = []
    if fwd:
        text, subject, attached = _forward(uid, fwd, str(body.get("folder") or "INBOX")[:200], text, subject,
                                           bool(body.get("files")))
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=acct["user"].rsplit("@", 1)[1])
    msg.set_content(text)
    for name, ctype, data in attached:
        main, _, sub = ctype.partition("/")
        msg.add_attachment(data, maintype=main, subtype=sub, filename=name)
    token = os.urandom(16).hex()
    with _lock:
        now = time.time()
        for k in [k for k, v in _pending.items() if now - v["t"] > PREVIEW_SECONDS or v["uid"] == uid]:
            _pending.pop(k, None)       # one sheet per profile: a new preview replaces the one before
        _pending[token] = {"uid": uid, "acct": acct["id"], "msg": msg, "n": len(to) + len(cc), "t": now}
    return {"token": token, "from": msg["From"], "to": to, "cc": cc, "subject": subject, "text": text,
            "files": [f"{name} ({max(1, len(data) // 1024)} KB)" for name, _, data in attached],
            "account": acct.get("name", ""), "n": len(to) + len(cc), "seconds": PREVIEW_SECONDS}


def _forward(uid, ref, folder, text, subject, with_files):
    """Weiterleiten: (text with the original below, subject "Fwd: …", [(name, type, bytes)] of its attachments).
    The original is data: its text is quoted as text, its files are attached as they are, never opened."""
    orig = mail.whole(uid, ref, folder)
    if orig is None:
        raise LookupError("the mail to forward is not there")
    old = mail._hdr(orig.get("Subject", ""))
    if not subject:
        subject = (old if re.match(r"(?i)(fwd?|wg)\s*:", old) else "Fwd: " + old)[:MAX_SUBJECT]
    own, _ = mail.plain(orig)
    head = (f"---------- Weitergeleitete Nachricht ----------\nVon: {mail._hdr(orig.get('From', ''))}\n"
            f"Datum: {mail._hdr(orig.get('Date', ''))}\nBetreff: {old}\nAn: {mail._hdr(orig.get('To', ''))}\n\n")
    text = ((text + "\n\n") if text else "") + head + own
    attached = []
    if with_files:
        for part, name, size in mail.files(orig):
            attached.append((name, part.get_content_type() if "/" in part.get_content_type() else "application/octet-stream",
                             part.get_payload(decode=True) or b""))
        if sum(len(d) for _, _, d in attached) > FORWARD_FILES:
            raise ValueError(f"attachments together at most {FORWARD_FILES // (1024 * 1024)} MB; forward without them")
    return text[:MAX_TEXT * 2], subject, attached


def send(uid, token):
    """Sends the mail of this profile's preview sheet, once. {"sent": n, "refused": n, "copy": sent folder or ""}."""
    who = profiles.log_name(profiles.by_id(uid))
    with _lock:
        p = _pending.get(str(token or ""))
        if not p or p["uid"] != uid or p.get("busy") or time.time() - p["t"] > PREVIEW_SECONDS:
            p = None
        else:
            p["busy"] = True            # one „Senden“ at a time; gone once sent, kept for another try when not
    if not p:
        print(f"mail: send refused, no preview | {who}", flush=True)
        raise LookupError("the preview is gone; look at the mail again")
    try:
        notaus.stop("aktion", uid)
        if _count(uid) >= MAX_DAY:
            raise ValueError(f"at most {MAX_DAY} mails a day")
        acct = next((a for a in mail.get(uid)["accounts"] if a["id"] == p["acct"]), None)
        if not acct:
            raise ValueError("unknown mailbox")
        refused = _smtp(acct, p["msg"])
    except notaus.NotausAktiv:
        p["busy"] = False               # nothing went out: the sheet may try again
        print(f"mail: send refused, notaus | {who}", flush=True)
        raise
    except ValueError:
        p["busy"] = False
        print(f"mail: send refused | {who}", flush=True)
        raise
    except Exception as e:
        with _lock:                     # unclear whether it went out: never a second time from this sheet
            _pending.pop(token, None)
        print(f"mail: send failed ({type(e).__name__}) | {who}", flush=True)
        raise
    with _lock:
        _pending.pop(token, None)
        _count(uid)
        _today["n"][uid] = _today["n"].get(uid, 0) + 1
        write_json(SENT_FILE, {"day": _today["day"], "n": dict(_today["n"])}, mode=0o600)
    print(f"mail: sent | {p['n'] - refused} recipients, {refused} refused | {who}", flush=True)
    copy = ""
    if outgoing(acct)[0] not in KEEPS_SENT:
        try:
            with tidy.Box(acct) as box:
                copy = box.special("\\sent", tidy.SENT_NAMES) or ""
                if copy:
                    typ, _ = box.c.append(tidy._q(box.boxes[copy]["raw"]), "(\\Seen)",
                                          imaplib.Time2Internaldate(time.time()), p["msg"].as_bytes())
                    copy = copy if typ == "OK" else ""
        except Exception as e:
            print(f"mail: sent copy failed ({type(e).__name__}) | {who}", flush=True)
            copy = ""
        else:
            print(f"mail: sent copy {'done' if copy else 'refused, no folder'} | {who}", flush=True)
    return {"sent": p["n"] - refused, "refused": refused, "copy": copy}


def _smtp(acct, msg):
    host, port = outgoing(acct)
    ctx = ssl.create_default_context()
    try:
        if port == 465:
            c = SMTP_SSL(host, port, timeout=TIMEOUT, context=ctx)
        else:
            c = SMTP(host, port, timeout=TIMEOUT)
            c.ehlo()
            if not c.has_extn("starttls"):
                c.close()
                raise ValueError("the outgoing server offers no TLS")
            c.starttls(context=ctx)
            c.ehlo()
    except (OSError, smtplib.SMTPException) as e:
        raise ValueError(f"outgoing server not reachable ({type(e).__name__})")
    try:
        try:
            c.login(acct["user"], acct.get("password", ""))
        except smtplib.SMTPAuthenticationError:
            raise ValueError("the outgoing server rejects the user name or password")
        return len(c.send_message(msg) or {})   # the others got it: refused ones are only counted
    except smtplib.SMTPServerDisconnected:
        raise ConnectionError("the outgoing server broke off; whether the mail went out is unclear")
    except smtplib.SMTPRecipientsRefused:
        raise ValueError("the outgoing server refused the recipients")
    except smtplib.SMTPException as e:
        raise ValueError(f"the outgoing server refused the mail ({type(e).__name__})")
    finally:
        try:
            c.quit()
        except Exception:
            pass


# ---------------------------------------------------------------- Senden per Sprache (fixed rules, never the model)
NAME = "senden"
PENDING_SECONDS = 5 * 60
READ_SECONDS = 15 * 60          # "Antworte ihr per Mail" counts this long after the assistant read a mail
LEVELS = ("off", "answers", "all")
_last_read = {}                 # uid → (t, mail id, src): the mail the assistant read last
_WITH_MAIL = r"(?:per\s+(?:e-?mail|mail)|by\s+(?:e-?mail|mail))"
REPLY = re.compile(r"(?is)^\s*(?:bitte\s+)?(?:antworte|antwort|reply)(?:\s+(?:ihm|ihr|ihnen|darauf|to\s+(?:him|her|them)))?"
                   r"\s+" + _WITH_MAIL + r"\s*[:,]?\s*(?P<text>.{1,4000}?)\s*$")
NEW = re.compile(r"(?is)^\s*(?:bitte\s+)?(?:(?:schreib(?:e)?|schick(?:e)?|sende|send|write)\s+(?:bitte\s+)?(?:eine|an|a)?\s*)?"
                 r"(?:e-?mail|mail)\s+(?:an|to)\s+(?P<to>[^:\n]{2,80}?)\s*[:,]\s*(?P<text>.{1,4000}?)\s*$")


def level():
    try:
        from common import load_config
        v = load_config().get("chat", {}).get("mail_send_voice", "off")
    except Exception:
        v = "off"
    return v if v in LEVELS else "off"


def note_read(uid, ref, src):
    """chat_tools.mail_tool: the assistant read this mail (for "Antworte ihr per Mail: …")."""
    if len(_last_read) > 1000:
        _last_read.clear()
    _last_read[uid] = (time.time(), str(ref), str(src or ""))


def parse(text):
    """("reply", text) or ("new", to, text) from the person's own words, else None."""
    m = REPLY.match(text or "")
    if m:
        return ("reply", m.group("text").strip())
    m = NEW.match(text or "")
    if m:
        return ("new", m.group("to").strip(), m.group("text").strip())
    return None


def pending(uid):
    return profiles.pending_get(uid, NAME, PENDING_SECONDS)


def drop_pending(uid):
    """Like messages.drop_pending: a proposal made by answer() in this very turn only loses its mark."""
    p = pending(uid)
    if p and p.pop("fresh", False):
        profiles._write(profiles.pending_file(uid, NAME), p)
        return
    profiles.pending_drop(uid, NAME)


def describe(p):
    return f"Mail an {p['label']}: „{p['text'][:300]}“"


def _note(call, system, proposed=True):
    r = {"call": {"name": "Mail senden " + call[0], "args": call[1], "result": call[2]}, "system": "Mail: " + system,
         "quiet": True}
    if proposed:
        r["proposed"] = NAME
    return r


def _subject(text):
    words = text.split()
    s = " ".join(words[:7])
    return (s[:80] + " …") if len(words) > 7 or len(s) > 80 else s


def offer(ctx):
    """No tool for the model: the panel's fixed rule (answer) recognizes the request in the person's own words."""
    return None


async def answer(ctx, latest):
    """The person's yes or no to a waiting mail, or a new one in their own words: {"call", "system", …} or None."""
    import asyncio
    who = ctx.get("who")
    if not who or not ctx.get("own") or not ctx.get("private", True) or level() == "off":
        return None
    uid, src = who["id"], ctx.get("src", "")
    if not features.allowed("mailsend", uid) or not features.allowed("mail", uid):
        return None
    log_who = profiles.log_name(profiles.by_id(uid))
    got = parse(latest)
    p = pending(uid)
    if p and p.get("src", src) == src and not got:
        import calendars
        profiles.pending_drop(uid, NAME)   # answered: gone, whatever its mark
        if not calendars.confirms(latest):
            print(f"mail: voice declined | {log_who}", flush=True)
            return _note(("(abgelehnt)", describe(p), "nicht gesendet"),
                         f"{describe(p)} wurde NICHT gesendet, weil der Nutzer nicht zugestimmt hat. Sag das kurz.", False)
        body = {"to": p["to"], "text": p["text"], "subject": p.get("subject", "")}
        body.update({"reply": p["reply"]} if p.get("reply") else {"account": p["account"]})
        try:
            prev = await asyncio.to_thread(preview, uid, body)
            done = await asyncio.to_thread(send, uid, prev["token"])
        except notaus.NotausAktiv:
            return _note(("(Notaus)", describe(p), "nicht gesendet"), "Notaus: gerade wird nichts gesendet. Sag dem Nutzer genau das.", False)
        except (ValueError, LookupError) as e:
            return _note(("(nicht möglich)", describe(p), str(e)[:120]),
                         f"Die Mail wurde NICHT gesendet ({str(e)[:120]}). Sag dem Nutzer das in einem Satz.", False)
        except Exception as e:
            return _note(("(Fehler)", describe(p), type(e).__name__),
                         "Der Postausgang brach ab; ob die Mail raus ist, steht im Ordner Gesendet. Sag dem Nutzer genau das.", False)
        print(f"mail: voice sent | {log_who}", flush=True)
        return _note(("(bestätigt)", describe(p), "gesendet"),
                     f"Die Mail an {p['label']} ist gesendet. Sag dem Nutzer genau das in einem Satz.", False)
    if not got:
        return None
    return _direct(uid, got, src, log_who)


def _refuse(why, note, log_who):
    print(f"mail: voice refused, {why} | {log_who}", flush=True)
    return _note(("(nicht möglich)", "", why), note + " Sag dem Nutzer genau das.", False)


def _direct(uid, got, src, log_who):
    accts = mail.get(uid)["accounts"]
    if got[0] == "reply":
        last = _last_read.get(uid)
        if not last or time.time() - last[0] > READ_SECONDS or last[2] != src:
            return None   # nothing read just now here: not this rule's (messages.py may take "Antworte ihm")
        try:
            orig = mail.message(uid, last[1])
        except ValueError:
            orig = None
        if orig is None:
            return _refuse("not found", "Die Mail, auf die du antworten willst, ist nicht mehr da.", log_who)
        _, addr = email.utils.parseaddr(mail._hdr(orig.get("From", "")))
        if not ADDR.fullmatch(addr or ""):
            return _refuse("no address", "Die Mail hat keinen Absender, dem ich antworten kann.", log_who)
        import contacts
        # the name only from the own contacts: the sender's name in the mail is someone else's text
        p = {"kind": "reply", "reply": last[1], "to": addr, "label": contacts.name_for(uid, addr) or addr,
             "text": got[1][:MAX_TEXT], "subject": ""}
    else:
        if level() != "all":
            return _refuse("level", "Neue Mails per Sprache sind aus; per Sprache geht nur Antworten "
                           "(Admin: Funktionen → E-Mail lesen → „Mails senden“ → Senden per Sprache).", log_who)
        to, text = got[1], got[2]
        if ADDR.fullmatch(to):
            addr, label = to, to
        else:
            import contacts
            hits = [x for x in contacts.search(uid, to) if x.get("emails")] if contacts.usable(uid) else []
            if len(hits) != 1 or len(hits[0]["emails"]) != 1:
                if len(hits) > 1:
                    names = " oder ".join(x["name"] for x in hits[:4])
                    return _refuse("several", f"Mehrere Kontakte passen ({names}). Sag den ganzen Namen.", log_who)
                if hits:
                    return _refuse("several addresses", f"{hits[0]['name']} hat mehrere Mail-Adressen. Sag die Adresse ganz.", log_who)
                return _refuse("not in contacts", f"{to} steht nicht mit einer Mail-Adresse in deinen Kontakten.", log_who)
            addr, label = hits[0]["emails"][0], hits[0]["name"]
        if not accts:
            return _refuse("no mailbox", "Es ist kein Postfach verbunden.", log_who)
        p = {"kind": "new", "account": accts[0]["id"], "to": addr, "label": label, "text": text[:MAX_TEXT], "subject": _subject(text)}
    if not ADDR.fullmatch(p["to"]):
        return _refuse("no address", "Das ist keine Mail-Adresse.", log_who)
    profiles.pending_set(uid, NAME, dict(p, fresh=True), src)
    print(f"mail: voice proposed | {log_who}", flush=True)
    return _note(("(Vorschlag)", describe(p), "wartet auf Ja"),
                 f"Noch NICHT gesendet. Frag den Nutzer genau: „Soll ich die Mail an {p['label']} senden: ‚{p['text'][:300]}‘?“ "
                 "Erst sein Ja in der nächsten Nachricht sendet sie.")
