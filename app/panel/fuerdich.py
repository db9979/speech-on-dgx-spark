"""Für dich (plan persoenlicher-assistent/plan.md, Dominik 2026-10-18 „1a 2a 3a 4a 5a 6a 7a“, stage 1): the Spark looks
through the profile's own mailboxes and finds what needs the person or is good to know:

    rechnung    a bill with an amount, with the day it is due (or "wird abgebucht")
    vertrag     a contract or subscription that renews, with the day and the last day to cancel
    bestellung  an order confirmation with shop and amount
    angebot     an offer or coupon with the last day it is valid
    antwort     a person the profile wrote to before asks something and got no answer for ANSWER_DAYS days
    verdacht    a mail that names a known brand but does not come from it (phishing)

Fixed rules, the panel decides, no model: the kind comes from the sender, the headers and fixed words; amounts and
days are read by patterns and kept only when they parse; every sentence on a card is a fixed sentence of this module
with the checked values in it. Sender names and subjects are outside text: the page shows them as text only, links
from a mail are never opened or shown as a link (only the domain, for the phishing warning).

Read only: tidy.Box without a tidying state (EXAMINE, BODY.PEEK), the inbox, the Spark folders Werbung, Newsletter
and Rechnungen when tidying made them, and the headers of the Sent folder (to know whom the profile wrote and what it
answered). Nothing is marked, moved or written. Off until the admin switches chat.mail_insight on (needs chat.mail);
then for every profile with a mailbox the admin did not block; guests never.

Kept: the last reading of each mailbox (the found items with their time, never a mail text) sealed in
users/<id>/fuerdich-vorrat.bin (vorrat.Vorrat, the one way for such a supply), so the tab shows it at once after a
restart and a mailbox that does not answer gives its items with „Stand hh:mm“ instead of „nicht erreichbar“ (Dominik
2026-10-20, part of the Mail-Vorrat); a mailbox's items go with the mailbox on the next reading, the file with
„Markierungen vergessen“, the profile, and after VORRAT_IDLE_DAYS without a reading. In users/<id>/fuerdich.json only
what the person pressed (erledigt / nicht interessant) as hashes of the Message-ID with the time, so a pressed card
does not come back.

    GET  /api/profile/fuerdich           {"items": [...], "counts": {...}, "errors": [...]} (?fresh=1 reads again)
    POST /api/profile/fuerdich/mark      {"id": ..., "as": "done" | "no" | "open"}
    DELETE /api/profile/fuerdich         forget the pressed marks
"""
import asyncio
import concurrent.futures
import datetime
import email
import email.policy
import email.utils
import hashlib
import imaplib
import json
import os
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import mail
import mailidle
import notaus
import profiles
import vorrang
from common import DayCounter
from vorrat import Vorrat
from core import assistant, browser_profile, json_body, own_profile

router = APIRouter()
KINDS = {"rechnung": ("Rechnung", "Bill"), "vertrag": ("Vertrag", "Contract"), "bestellung": ("Bestellung", "Order"),
         "angebot": ("Angebot", "Offer"), "antwort": ("Antwort offen", "Reply missing"), "verdacht": ("Verdacht", "Suspicious")}
URGENT = ("verdacht", "rechnung", "vertrag", "antwort")   # "Braucht dich"; the rest is "Gut zu wissen"
DAYS = 30                       # mails of the last 30 days (mail.DAYS)
SCAN = 300                      # newest messages per folder whose headers are read
BODIES = 60                     # at most this many mail texts are read per mailbox and run
RAW = 60000                     # bytes of one mail
CACHE_SECONDS = 600
STALE_SECONDS = 24 * 3600       # the tab shows an older reading at once and reads anew in the background; a mailbox
                                # that does not answer gives its kept items up to this old (with „Stand hh:mm“)
VORRAT = "fuerdich-vorrat.bin"  # the last reading per mailbox, sealed in the profile's folder (dateien.py)
VORRAT_IDLE_DAYS = 14           # deleted when nobody read „Für dich“ for this long (mailvorrat.IDLE_DAYS)
SWEEP_EVERY = 24 * 3600
VIEW_BUDGET = 8.0               # seconds the tab waits for a first reading, then „lädt noch“ (fuerdich.js asks again)
ANSWER_DAYS = 2                 # a question waits this long before it is a card
ANSWER_MAX = 14                 # and is not one any more after this
OFFER_AHEAD = 14                # an offer is shown when it ends within these days
MAX_OFFERS = 5
MAX_ITEMS = 40
MARKS_MAX = 2000
FOLDERS = ("werbung", "newsletter", "rechnungen")   # tidy.py categories that are read besides the inbox
SENT_FIELDS = "TO CC DATE IN-REPLY-TO REFERENCES"

AMOUNT = re.compile(r"(?:(?:€|EUR)\s?(\d{1,3}(?:\.\d{3})*(?:,\d{2})|\d+(?:,\d{2}))|"
                    r"(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})\s?(?:€|EUR|Euro))", re.I)
AMOUNT_NEAR = re.compile(r"(?i)(gesamt|summe|betrag|zu zahlen|rechnungsbetrag|endbetrag|total|zahlbetrag|preis|monatlich|pro monat)")
MONTHS = {m: i + 1 for i, m in enumerate(["januar", "februar", "märz", "april", "mai", "juni", "juli", "august",
                                           "september", "oktober", "november", "dezember"])}
DATE = re.compile(r"\b(\d{1,2})\.\s?(\d{1,2})\.(\d{4}|\d{2})?(?!\d)|\b(\d{1,2})\.\s?(" + "|".join(MONTHS) +
                  r")(?:\s(\d{4}))?", re.I)
BILL = re.compile(r"(?i)\b(rechnung|zahlungserinnerung|mahnung|lastschrift|abbuchung|beitragsrechnung|"
                  r"invoice|payment due|zahlungsaufforderung)")
BILL_DUE = re.compile(r"(?i)(fällig (?:am|zum|bis)|zahlbar bis|bis (?:zum|spätestens)|zahlungsziel|spätestens (?:am|bis)|"
                      r"due (?:date|on|by))[^\n]{0,30}")
DEBIT = re.compile(r"(?i)(lastschrift|wird (?:von ihrem|von deinem|vom) konto|abgebucht|eingezogen|abbuchung)")
CONTRACT = re.compile(r"(?i)\b(vertrag|abo|abonnement|mitgliedschaft|tarif|laufzeit|subscription)")
RENEW = re.compile(r"(?i)(verlängert sich|verlängerung|automatisch verlängert|kündig|laufzeitende|vertragsende|"
                   r"preisanpassung|preiserhöhung|renew)")
RENEW_DAY = re.compile(r"(?i)(verlängert sich[^.\n]{0,15}am|verlängerung am|laufzeitende|vertragsende|endet am|"
                       r"läuft[^.\n]{0,12}bis|renews on)[^\n]{0,30}")
CANCEL_DAY = re.compile(r"(?i)(kündig\w*[^.\n]{0,25}bis|kündigungsfrist[^.\n]{0,10}bis|cancel by)[^\n]{0,30}")
ORDER = re.compile(r"(?i)(bestellbestätigung|ihre bestellung|deine bestellung|bestellung (?:nr|nummer|eingegangen)|"
                   r"danke für (?:ihre|deine) bestellung|vielen dank für (?:ihre|deine) bestellung|order confirmation|"
                   r"your order)")
OFFER = re.compile(r"(?i)(gutschein|rabatt|\b\d{1,2}\s?%|\bsale\b|aktion|angebot|coupon|code)")
OFFER_END = re.compile(r"(?i)(gültig bis|nur bis|endet am|bis einschließlich|einlösbar bis|läuft bis|valid until|"
                       r"bis zum|nur noch bis)[^\n]{0,30}")
NOREPLY = re.compile(r"(?i)^(no-?reply|do-?not-?reply|noreply|notification|notifications|newsletter|news|info|service|"
                     r"support|kundenservice|mailer-daemon|postmaster|bounce|team|hello|hallo|kontakt)[@.+-]")
QUESTION = re.compile(r"\?\s*(?:$|\n)|\?\s+[A-ZÄÖÜ]", re.M)
ACTION = re.compile(r"(?i)(bestätig|verifizier|gesperrt|sperrung|eingeschränkt|aktualisier|ungewöhnliche aktivität|"
                    r"sicherheitsüberprüfung|zugangsdaten|passwort|kontodaten|zahlungsdaten|klicken sie|klicke|verify|"
                    r"suspended|unusual activity|update your)")
HREF = re.compile(r"""(?i)href\s*=\s*["']?https?://([a-z0-9.\-]{3,253})""")
URL = re.compile(r"(?i)https?://([a-z0-9.\-]{3,253})")
# brand word -> domains that really send its mails (phishing check; a forged header is caught by parcels.forged too)
BRANDS = {"sparkasse": ("sparkasse.de", "s-payment.de", "sparkassen-finanzportal.de"), "paypal": ("paypal.com", "paypal.de"),
          "amazon": ("amazon.de", "amazon.com", "amazonses.com"), "dhl": ("dhl.de", "dhl.com", "deutschepost.de"),
          "apple": ("apple.com", "icloud.com", "me.com"), "telekom": ("telekom.de", "t-online.de"),
          "volksbank": ("vr.de", "volksbank.de", "vrbank.de"), "commerzbank": ("commerzbank.de", "comdirect.de"),
          "ing": ("ing.de", "ing.com"), "dkb": ("dkb.de",), "netflix": ("netflix.com",), "microsoft": ("microsoft.com",
          "outlook.com", "office.com"), "post": ("deutschepost.de", "dhl.de"), "ebay": ("ebay.de", "ebay.com"),
          "postbank": ("postbank.de",), "vodafone": ("vodafone.de", "vodafone.com"), "elster": ("elster.de",)}
SALT = "fuerdich-v1"

_lock = threading.Lock()
# uid -> {"at": time of the last reading, "boxes": {mailbox id: {"at", "items"}}, "errors": [[name, why]]}; written on
# every reading (at most every CACHE_SECONDS, unless the person asks for a fresh one)
_v = Vorrat(VORRAT, VORRAT_IDLE_DAYS, write_every=0, empty=lambda: {"at": 0, "boxes": {}, "errors": []})
_swept = [0.0]
_day = DayCounter()             # per day: runs, found, failed, marked, vorrat (Zustand → Live)


# ---------------------------------------------------------------- the pressed marks
def _file(uid):
    return profiles._path(uid, "fuerdich.json")


def marks(uid):
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    m = d.get("marks") if isinstance(d, dict) else None
    return {k: v for k, v in (m or {}).items() if isinstance(k, str) and re.fullmatch(r"[0-9a-f]{20}", k)
            and isinstance(v, list) and len(v) == 2 and v[0] in ("done", "no") and isinstance(v[1], (int, float))}


def _save(uid, m):
    with _lock:
        if len(m) > MARKS_MAX:   # the oldest marks go first
            m = dict(sorted(m.items(), key=lambda kv: kv[1][1])[-MARKS_MAX:])
        profiles._write(_file(uid), {"marks": m})


def count(uid):
    """Pressed marks (features.OWN, Daten löschen): a number, never contents."""
    return len(marks(uid))


def forget(uid):
    try:
        os.remove(_file(uid))
    except OSError:
        pass
    _v.forget(uid)          # the kept reading goes with the marks („Markierungen vergessen“)


features.OWN["fuerdich"] = (count, forget)


def key(mid, aid="", uidn=0):
    v = (mid or "").strip() or f"{aid}:{uidn}"
    return hashlib.sha256((SALT + v).encode()).hexdigest()[:20]


# ---------------------------------------------------------------- fixed rules
def domain(sender):
    m = re.search(r"@([\w.\-]+)", sender or "")
    return (m.group(1) if m else "").lower().strip(".")


def _of(dom, domains):
    return any(dom == d or dom.endswith("." + d) for d in domains)


def who(sender):
    """The name a card shows: the display name, else the domain (outside text, cut)."""
    name, addr = email.utils.parseaddr(sender or "")
    name = re.sub(r"[\x00-\x1f<>\"]", "", name).strip()
    return (name or domain(sender) or addr)[:40]


def amount(text):
    """The amount next to a fixed word (Gesamt, Betrag …), else the first one; '84,20 €' or ''."""
    best = None
    for m in AMOUNT.finditer(text):
        v = m.group(1) or m.group(2)
        try:
            n = float(v.replace(".", "").replace(",", "."))
        except ValueError:
            continue
        if not 0 < n < 100000:
            continue
        near = bool(AMOUNT_NEAR.search(text[max(0, m.start() - 40):m.start()]))
        if best is None or (near and not best[0]):
            best = (near, n)
        if near:
            break
    return f"{best[1]:.2f} €".replace(".", ",") if best else ""


def _date(m, sent):
    try:
        if m.group(1):
            y = int(m.group(3)) if m.group(3) else sent.year
            y = y + 2000 if y < 100 else y
            d = datetime.date(y, int(m.group(2)), int(m.group(1)))
        else:
            y = int(m.group(6)) if m.group(6) else sent.year
            d = datetime.date(y, MONTHS[m.group(5).lower()], int(m.group(4)))
    except (ValueError, TypeError):
        return None
    if not m.group(3) and not (m.group(6) if m.group(4) else None) and d < sent - datetime.timedelta(days=60):
        d = d.replace(year=d.year + 1)    # "bis 05.01." in a mail of December
    return d


def day_after(pattern, text, sent):
    """The first date in the words right after a fixed phrase ("fällig am 24.10.2026"), else None."""
    for m in pattern.finditer(text):
        d = DATE.search(m.group(0))
        if d:
            x = _date(d, sent)
            if x and abs((x - sent).days) < 800:
                return x
    return None


def links(raw, text):
    """The domains the mail's links lead to (href in HTML, bare addresses in the text)."""
    return {m.group(1).lower().strip(".") for m in HREF.finditer(raw or "")} | \
        {m.group(1).lower().strip(".") for m in URL.finditer(f"{raw or ''}\n{text or ''}")}


def signed(msg, sender):
    """True when the own mail server says the sender's own domain sent this mail: DMARC pass, or DKIM pass signed by
    that domain, or SPF pass for it (the top Authentication-Results header). Without one nothing can be told."""
    dom = domain(sender)
    try:
        ar = str((msg.get_all("Authentication-Results") or [""])[0]).lower()
    except Exception:
        return False
    if not dom or not ar:
        return False
    if re.search(r"\bdmarc=pass\b", ar):
        return True
    for kind, key in (("dkim", "header.d"), ("spf", "smtp.mailfrom")):
        for m in re.finditer(kind + r"=pass\b[^;]*?" + re.escape(key) + r"=(?:[^@\s;]*@)?([a-z0-9.\-]+)", ar):
            d = m.group(1).strip(".")
            if d and (_of(dom, (d,)) or _of(d, (dom,))):
                return True
    return False


def suspicious(sender, subject, text, link_domains, forged=False, signed_by_sender=False):
    """The brand a mail pretends to come from, when it does not; '' when it looks fine. Pretending is the brand in
    the sender's name (or a forged header); a brand only in the subject is a mail about it (an o2 offer with Netflix,
    Dominik 2026-10-20) and counts only when the sender's own domain did not verifiably send the mail or the subject
    itself asks to confirm, log in or says the account is blocked."""
    dom = domain(sender)
    name = email.utils.parseaddr(sender or "")[0].lower()
    for brand, domains in BRANDS.items():
        word = r"\b" + re.escape(brand) + r"\b"
        in_name = bool(re.search(word, name)) or (bool(re.search(word, dom)) and not _of(dom, domains))   # name or lookalike domain
        if not in_name and not re.search(word, (subject or "").lower()):
            continue
        if forged:
            return brand
        if not in_name and not _of(dom, domains) and signed_by_sender and not ACTION.search(subject or ""):
            continue                # its own domain sent it and only names the brand: an offer, a partner, news
        if _of(dom, domains):
            foreign = [d for d in link_domains if not _of(d, domains) and not _of(d, (dom,))]
            if foreign and ACTION.search(f"{subject}\n{text}") and len(foreign) == len(link_domains):
                return brand        # all links lead elsewhere and it asks to log in or confirm
            return ""
        if ACTION.search(f"{subject}\n{text}"):
            return brand
    return ""


def classify(h, text, sent, today, raw="", forged=False, signed_by_sender=False):
    """One item {kind, ...} of a mail or None. h: {"from", "subject", "bulk", "cat"} (cat: the tidy folder)."""
    frm, subj = h.get("from", ""), h.get("subject", "")
    s = f"{subj}\n{text[:6000]}"
    brand = suspicious(frm, subj, text, links(raw, text), forged, signed_by_sender)
    if brand:
        return {"kind": "verdacht", "brand": brand.capitalize() if len(brand) > 3 else brand.upper(),
                "domain": domain(frm)[:60]}
    if forged:
        return None
    if ORDER.search(subj) and not BILL.search(subj):
        return {"kind": "bestellung", "amount": amount(s)}
    if CONTRACT.search(s) and RENEW.search(s) and (RENEW_DAY.search(s) or CANCEL_DAY.search(s)):
        renew, cancel = day_after(RENEW_DAY, s, sent), day_after(CANCEL_DAY, s, sent)
        if (renew and renew >= today) or (cancel and cancel >= today):
            return {"kind": "vertrag", "amount": amount(s), "day": renew.isoformat() if renew else "",
                    "cancel": cancel.isoformat() if cancel and cancel >= today else ""}
    if BILL.search(subj) or (h.get("cat") == "rechnungen" and BILL.search(s)):
        a = amount(s)
        if a:
            due = day_after(BILL_DUE, s, sent)
            debit = bool(DEBIT.search(s))
            if due and due < today - datetime.timedelta(days=1) and not debit:
                return None             # long past: nothing to do any more
            return {"kind": "rechnung", "amount": a, "day": due.isoformat() if due else "", "debit": debit}
    if h.get("bulk") or h.get("cat") in ("werbung", "newsletter"):
        if OFFER.search(s):
            end = day_after(OFFER_END, s, sent)
            if end and today <= end <= today + datetime.timedelta(days=OFFER_AHEAD):
                return {"kind": "angebot", "day": end.isoformat()}
    return None


def asks(h, sent_dt, now, answered, wrote_to):
    """The header part of "Antwort offen": a person the profile wrote to before, no answer since, not too old."""
    addr = email.utils.parseaddr(h.get("from", ""))[1].lower()
    if not addr or h.get("bulk") or h.get("auto") or NOREPLY.search(addr) or addr not in wrote_to:
        return False
    age = (now - sent_dt).total_seconds() / 86400
    if not ANSWER_DAYS <= age <= ANSWER_MAX:
        return False
    if h.get("mid") and h["mid"] in answered:
        return False
    return wrote_to.get(addr, 0) <= sent_dt.timestamp()     # else the profile wrote to this person afterwards


def waiting(h, text, sent_dt, now, answered, wrote_to):
    """True when such a person asks something in the own text of the mail (quotes are cut by mail.plain)."""
    return asks(h, sent_dt, now, answered, wrote_to) and bool(QUESTION.search(text[:1500]))


# ---------------------------------------------------------------- reading the mailboxes
def _bulk(m):
    return bool(m.get("List-Unsubscribe") or m.get("List-Id") or str(m.get("Precedence") or "").lower() in ("bulk", "list")
                or m.get("Feedback-ID") or m.get("X-Campaign") or m.get("X-Newsletter"))


def _sent(b):
    """({message ids the profile answered}, {address: time of the newest mail to it}) from the Sent folder's headers."""
    import tidy
    folder = b.special("\\sent", tidy.SENT_NAMES)
    answered, wrote = set(), {}
    if not folder:
        return answered, wrote
    b.select(folder)                    # EXAMINE
    uids = sorted(b.search("SINCE", tidy._since(365)))[-2000:]
    for m in b.headers(uids, SENT_FIELDS).values():
        t = mail._date(m.get("Date")).timestamp()
        for ref in re.findall(r"<[^<>\s]{3,200}>", f"{m.get('In-Reply-To') or ''} {m.get('References') or ''}"):
            answered.add(ref)
        for _, a in email.utils.getaddresses([str(m.get("To", "")), str(m.get("Cc", ""))]):
            a = a.strip().lower()
            if "@" in a:
                wrote[a] = max(wrote.get(a, 0), t)
    return answered, wrote


def _fetch(b, uidn):
    typ, data = b.c.uid("FETCH", str(uidn), f"(BODY.PEEK[]<0.{RAW}>)")
    raw = next((p[1] for p in data if isinstance(p, tuple) and p[1]), None) if typ == "OK" else None
    return email.message_from_bytes(raw, policy=email.policy.default) if raw else None


def _raw_text(msg):
    """The text and HTML parts as they came (mail.plain shortens long links), only to read the links' domains."""
    out = []
    for part in msg.walk():
        if part.get_content_type() in ("text/html", "text/plain"):
            try:
                out.append(str(part.get_content())[:RAW])
            except Exception:
                pass
    return "\n".join(out)[:2 * RAW]


def _shop(shops, h):
    """Counts a shop's orders, offers and newsletters from the header alone (Was ich über dich weiß, ichweiss.py), with
    the topics its subjects and domain name (ichweiss.TOPICS), whether it is a service or machine sender, and up to
    ichweiss.EXAMPLES subjects of its offers and newsletters (memory only, shown as evidence)."""
    import ichweiss     # the topics are its list; it imports this module
    subj, name = h["subject"], who(h["from"])
    what = "orders" if ORDER.search(subj) else "offers" if (h["bulk"] or h["cat"]) and OFFER.search(subj) else \
        "news" if h["bulk"] or h["cat"] in ("werbung", "newsletter") else ""
    if what and name and len(shops) < 300:
        c = shops.setdefault(name, {})
        c[what] = c.get(what, 0) + 1
        c["addr"] = email.utils.parseaddr(h["from"])[1].lower()[:200]
        if h.get("auto"):
            c["svc"] = True
        for k in ichweiss.topics_in(f"{name} {subj}", domain(h["from"])):
            c.setdefault("topics", {})[k] = c.get("topics", {}).get(k, 0) + 1
        ex = c.setdefault("ex", [])
        if what != "orders" and subj and len(ex) < ichweiss.EXAMPLES:
            ex.append(_one(subj, ichweiss.EXAMPLE_MAX))


def _account(acct, uid, today, now, shops=None):
    import mailregeln
    import parcels
    import tidy
    out = []
    with tidy.Box(acct) as b:           # no tidying state: nothing can be changed
        answered, wrote = _sent(b)
        boxes = [("INBOX", "")]
        try:
            d = tidy.state(uid)
            for cat in FOLDERS:
                f = tidy.folder_of(d, cat)
                if f and b.name(f) in b.boxes:
                    boxes.append((b.name(f), cat))
        except Exception:
            pass
        read = 0
        for box, cat in boxes:
            notaus.stop("gespraech")
            b.select(box)               # EXAMINE
            uids = sorted(b.search("SINCE", tidy._since(DAYS)))[-SCAN:]
            heads = b.headers(uids, tidy.HEAD_FIELDS + " AUTO-SUBMITTED")
            for n in sorted(heads, reverse=True):
                if read >= BODIES:
                    break
                m = heads[n]
                h = {"from": mail._addr(m.get("From", "")), "subject": mail._hdr(m.get("Subject", "")),
                     "bulk": _bulk(m), "cat": cat, "mid": str(m.get("Message-ID") or "").strip()[:200],
                     "auto": str(m.get("Auto-Submitted") or "no").lower() != "no"}
                sent_dt = mail._date(m.get("Date"))
                subj = h["subject"]
                if mailregeln.quiet(uid, h["from"], subj):   # a mail rule says „nicht in Für dich“ (mailregeln.py)
                    continue
                if shops is not None:
                    _shop(shops, h)
                person = asks(h, sent_dt, now, answered, wrote)
                if not (person or BILL.search(subj) or ORDER.search(subj) or CONTRACT.search(subj) or
                        any(re.search(r"\b" + br + r"\b", f"{h['from']} {subj}".lower()) for br in BRANDS) or
                        ((h["bulk"] or cat) and OFFER.search(subj))):
                    continue
                msg = _fetch(b, n)
                read += 1
                if msg is None:
                    continue
                text, _ = mail.plain(msg)
                sent = mail.local(sent_dt).date()
                x = None
                if person and waiting(h, text, sent_dt, now, answered, wrote):
                    x = {"kind": "antwort", "days": int((now - sent_dt).total_seconds() // 86400)}
                if x is None:
                    x = classify(h, text, sent, today, _raw_text(msg), parcels.forged(msg), signed(msg, h["from"]))
                if x:
                    x.update(id=key(h["mid"], acct["id"], n), who=who(h["from"]), subject=subj[:90],
                             sent=sent.isoformat(), at=int(sent_dt.timestamp()), ref=f"{acct['id']}:{n}", box=box,
                             addr=email.utils.parseaddr(h["from"])[1].lower()[:200])
                    out.append(x)
    print(f"fuerdich: postfach gelesen ordner={len(boxes)} mails={read} funde={len(out)}", flush=True)
    return out


_shops = {}                     # uid -> {shop name: {"orders", "offers", "news"}} of the last reading (memory only)


def shops(uid):
    """Per shop how many orders, offers and newsletters the last reading saw (ichweiss.proposals); names only."""
    return _shops.get(uid, {})


def _order(found, pressed):
    """Newest first, each once, without pressed ones, at most MAX_OFFERS offers and MAX_ITEMS items."""
    seen, items = set(), []
    for x in sorted(found, key=lambda x: x["at"], reverse=True):
        if x["id"] in seen or x["id"] in pressed:
            continue
        seen.add(x["id"])
        items.append(x)
    offers = [x for x in items if x["kind"] == "angebot"][MAX_OFFERS:]
    return [x for x in items if x not in offers][:MAX_ITEMS]


def _last(uid):
    """(time, (items, errors)) of the last reading (memory, else the sealed file after a restart), or None."""
    d = _v.load(uid)
    if not d.get("at"):
        return None
    found = [x for b in d["boxes"].values() for x in b["items"]]
    return d["at"], (_order(found, marks(uid)), [tuple(e) for e in d["errors"]])


def _keep(uid, boxes, errors, at):
    """Keeps a reading (the only way, scan and tests); the file is written at once, sealed."""
    with _v.lock:
        d = _v.load(uid)
        d.update(at=at, boxes=boxes, errors=[list(e) for e in errors])
        try:
            _v.changed(uid, force=True)
        except OSError:
            print("fuerdich: vorrat nicht geschrieben", flush=True)
    if at - _swept[0] > SWEEP_EVERY:
        _swept[0] = at
        try:
            n = _v.sweep()
            print(f"fuerdich: vorrat aufgeraeumt dateien={n}", flush=True)
        except OSError:
            print("fuerdich: vorrat aufraeumen fehler", flush=True)


def stand_word(at, today=None):
    """„14:20“ for a time of today, „19.10. 14:20“ for an older one (local time)."""
    t = mail.local(datetime.datetime.fromtimestamp(at, datetime.timezone.utc))
    return f"{t:%H:%M}" if t.date() == (today or datetime.date.today()) else f"{t:%d.%m. %H:%M}"


def scan(uid, today=None, now=None, force=False):
    """(items newest first without pressed ones, [(mailbox name, error)]). force: read anew whatever was read last
    (the last reading stays until the new one replaces it, so the tab keeps showing it meanwhile). A mailbox that
    does not answer keeps its last items (up to STALE_SECONDS old) and says „Stand hh:mm“ in its error."""
    hit = _last(uid)
    if hit and time.time() - hit[0] < CACHE_SECONDS and today is None and not force:
        return hit[1]
    today = today or datetime.date.today()
    now = now or datetime.datetime.now(datetime.timezone.utc)
    errors, shop, boxes, t = [], {}, {}, time.time()
    kept = _v.load(uid)["boxes"]

    def one(a):
        try:
            return _account(a, uid, today, now, shop), None
        except (ValueError, OSError, imaplib.IMAP4.error) as e:
            return [], (a.get("name", ""), "nicht_lesbar" if isinstance(e, ValueError) else type(e).__name__)
    accts = mail.get(uid)["accounts"]
    # all mailboxes at the same time (Dominik 2026-10-19 „dauert länger als sonst“), each its own IMAP session
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(accts))) as ex:
        for a, (got, err) in zip(accts, ex.map(one, accts)):
            old = kept.get(a.get("id"))
            if not err:
                boxes[a["id"]] = {"at": t, "items": got}
            elif old and t - old["at"] < STALE_SECONDS and old["items"]:
                boxes[a["id"]] = old       # its last items, said with their time (never „nicht erreichbar“ alone)
                errors.append((err[0], f"antwortet gerade nicht, Einträge von Stand {stand_word(old['at'], today)}"))
                _bump("vorrat")
                print(f"fuerdich: postfach aus vorrat {profiles.log_name(profiles.by_id(uid))}", flush=True)
            else:
                errors.append(err)
    _keep(uid, boxes, errors, t)          # a removed mailbox's items are gone with this reading
    if len(_shops) > 200:
        _shops.clear()
    _shops[uid] = shop
    return _last(uid)[1]


# ---------------------------------------------------------------- fixed sentences
WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def day_word(iso, today):
    d = datetime.date.fromisoformat(iso)
    k = (d - today).days
    return "heute" if k == 0 else "morgen" if k == 1 else f"{WEEKDAYS[d.weekday()]} {d.day}.{d.month}." if 0 < k < 7 \
        else f"{d.day}.{d.month}.{d.year}" if d.year != today.year else f"{d.day}.{d.month}."


def sentence(x, today):
    """(title, line) of a card, built only from checked values."""
    k, w = x["kind"], x.get("who", "")
    if k == "verdacht":
        return (f"Vorsicht: Mail gibt sich als {x['brand']} aus",
                f"Sie kommt von {x['domain'] or 'einer fremden Adresse'}. Links darin nicht öffnen.")
    if k == "rechnung":
        if x.get("debit"):
            return f"Rechnung {w}: {x['amount']}", "Wird laut Mail abgebucht, du musst nichts tun."
        if x.get("day"):
            late = datetime.date.fromisoformat(x["day"]) < today
            return (f"Rechnung {w}: {x['amount']} bis {day_word(x['day'], today)}",
                    "Die Frist ist vorbei." if late else f"Noch {(datetime.date.fromisoformat(x['day']) - today).days} Tage.")
        return f"Rechnung {w}: {x['amount']}", "Keine Frist in der Mail gefunden."
    if k == "vertrag":
        t = f"{w}: Vertrag verlängert sich {'am ' + day_word(x['day'], today) if x.get('day') else 'bald'}"
        line = f"Kündigen geht bis {day_word(x['cancel'], today)}." if x.get("cancel") else "Keine Kündigungsfrist in der Mail gefunden."
        return t, line + (f" Betrag laut Mail: {x['amount']}." if x.get("amount") else "")
    if k == "bestellung":
        return f"Bestellung bei {w}" + (f": {x['amount']}" if x.get("amount") else ""), f"Mail vom {day_word(x['sent'], today)}"
    if k == "angebot":
        return f"Angebot von {w}, gültig bis {day_word(x['day'], today)}", "Steht in der Mail."
    if k == "antwort":
        # who waits for whom stays unmistakable when read aloud (Dominik 2026-10-20: „ich soll auf Anna warten“)
        return (f"{w} hat dir vor {x['days']} Tagen eine Frage geschickt und wartet auf deine Antwort",
                "Du hast darauf noch nicht geantwortet.")
    return w, ""


def public(uid, items, errors, today=None):
    import ichweiss
    today = today or datetime.date.today()
    wiss = features.allowed("ichweiss", uid)
    out = []
    for x in items:
        title, line = sentence(x, today)
        out.append({"id": x["id"], "kind": x["kind"], "urgent": x["kind"] in URGENT, "title": title, "line": line,
                    "who": x.get("who", ""), "subject": x.get("subject", ""), "sent": x["sent"], "day": x.get("day", ""),
                    "amount": x.get("amount", ""), "ref": x.get("ref", ""), "folder": x.get("box", "INBOX"), "addr": x.get("addr", ""),
                    "acts": acts(uid, x), "event": event_line(x, today),
                    "fits": ichweiss.fits(uid, x.get("who", ""), x.get("subject", ""), x.get("addr", "")) if wiss and x["kind"] in SHOP_KINDS else ""})
    # an offer that fits a confirmed interest comes first among the offers (stage 3, „3a 4a“)
    out.sort(key=lambda y: (not y["urgent"], not y["fits"], y["day"] or "9999", y["sent"]))
    counts = {k: sum(1 for y in out if y["kind"] == k) for k in KINDS}
    res = {"items": out, "counts": counts, "errors": [f"{n}: {e}" for n, e in errors]}
    if wiss:                    # Diesen Monat (7a) and the tip from the web (4a) at the end of the tab
        m = ichweiss.month_sum(items, today)
        res.update(month=dict(m, line=ichweiss.month_line(m)), tip=ichweiss.tip_of(uid))
    return res


# ---------------------------------------------------------------- stage 2: the buttons (Dominik 2026-10-18 „5a“)
# Erinnern sets a reminder with a fixed text, Eintragen hands a fixed line to „Schnell eintragen“ of the page Kalender
# (only its „Eintragen“ saves), Antwort entwerfen opens the answer with the Antwortvorschläge of the mail page,
# Kündigung entwerfen a new mail with a fixed text; both send only from the preview sheet of the mail page (senden.py).
REMIND_KINDS = ("rechnung", "vertrag", "angebot", "antwort")
REMIND_HOUR = 9                 # a reminder rings at 9 o'clock on the day before the deadline
REMIND_SOON = 3600              # never sooner than this from now
SHOP_KINDS = ("bestellung", "angebot")   # „Mehr davon“ makes the shop a confirmed interest (ichweiss.py)
NOSEND = re.compile(r"(?i)^(no-?reply|do-?not-?reply|mailer-daemon|postmaster|bounce\w*)[@.+-]")   # no cancelling mail goes there


def deadline(x):
    """The day that matters on a card (iso or ""): the last day to cancel, else the day it is due or ends."""
    if x.get("kind") == "rechnung" and x.get("debit"):
        return ""
    if x.get("kind") not in ("rechnung", "vertrag", "angebot"):
        return ""
    return x.get("cancel") or x.get("day") or ""


def _one(v, n=60):
    return re.sub(r"[\x00-\x1f]+", " ", str(v or "")).strip()[:n]


def acts(uid, x):
    """The buttons a card has, by fixed rules: what the kind allows and the switches this profile may use."""
    k, out = x["kind"], []
    if k in REMIND_KINDS and not (k == "rechnung" and x.get("debit")) and features.allowed("reminders", uid):
        out.append("remind")
    if deadline(x) and features.allowed("calendar", uid):
        out.append("event")
    if k == "antwort" and x.get("box", "INBOX") == "INBOX" and x.get("ref") and features.allowed("mailsend", uid):
        out.append("reply")
    if k == "vertrag" and features.allowed("mailsend", uid):
        out.append("cancel")
    if k in SHOP_KINDS and x.get("who") and features.allowed("ichweiss", uid):
        import ichweiss
        if not ichweiss.known(uid, x["who"]):
            out.append("more")
    return out


def remind_text(x):
    k, w = x["kind"], _one(x.get("who"), 40)
    if k == "rechnung":
        return f"Rechnung {w} bezahlen" + (f" ({x['amount']})" if x.get("amount") else "")
    if k == "vertrag":
        return f"Vertrag {w}: kündigen oder behalten?"
    if k == "angebot":
        return f"Angebot von {w} läuft ab"
    return f"{w} antworten"


def remind_at(x, now):
    """When the reminder rings (epoch seconds): 9 o'clock the day before the deadline, else tomorrow at 9; never
    sooner than REMIND_SOON from now. now: aware datetime in the person's zone."""
    d = deadline(x)
    day = datetime.date.fromisoformat(d) - datetime.timedelta(days=1) if d else now.date() + datetime.timedelta(days=1)
    at = datetime.datetime.combine(day, datetime.time(REMIND_HOUR), now.tzinfo)
    if at.timestamp() < now.timestamp() + REMIND_SOON:
        at = now + datetime.timedelta(seconds=REMIND_SOON) if d and d >= now.date().isoformat() else \
            datetime.datetime.combine(now.date() + datetime.timedelta(days=1), datetime.time(REMIND_HOUR), now.tzinfo)
    return int(at.timestamp())


def event_line(x, today):
    """The line for „Schnell eintragen“ (calendars.quick reads it): the day and fixed words, or ""."""
    d = deadline(x)
    if not d:
        return ""
    day = datetime.date.fromisoformat(d)
    what = {"rechnung": "Rechnung", "vertrag": "Kündigungsfrist" if x.get("cancel") else "Vertrag verlängert sich",
            "angebot": "Angebot endet"}[x["kind"]]
    # only letters and spaces of the name: a digit, a time or „in …“ would be read as a day, an hour or a place
    w = " ".join(re.sub(r"[^\w\s&-]|\d|_", " ", _one(x.get("who"), 40)).split())
    w = re.sub(r"(?i)\b(in|im|bei|beim|at|am|um|on)\b", " ", w)
    return f"{day.day}.{day.month}.{day.year} {what} {' '.join(w.split())}".strip()


def cancel_draft(uid, x, today):
    """A new mail that cancels the contract: fixed sentences with the checked values, to the sender unless it is a
    no-reply address. The person reads and changes it; only the preview sheet sends."""
    prof = profiles.by_id(uid) or {}
    w = _one(x.get("who"), 40)
    end = f"zum {datetime.date.fromisoformat(x['day']):%d.%m.%Y}" if x.get("day") else "zum nächstmöglichen Zeitpunkt"
    addr = x.get("addr", "")
    return {"to": "" if NOSEND.match(addr) else addr, "subject": f"Kündigung meines Vertrags bei {w}"[:120],
            "text": "Sehr geehrte Damen und Herren,\n\n"
                    f"hiermit kündige ich meinen Vertrag bei {w} fristgerecht {end}.\n"
                    "Bitte bestätigen Sie mir die Kündigung und das Vertragsende schriftlich.\n\n"
                    "Mit freundlichen Grüßen\n" + _one(prof.get("name"), 80)}


def find(uid, k):
    """The item with this id from the last reading, or None (the page shows only what is in it)."""
    hit = _last(uid)
    return next((x for x in (hit[1][0] if hit else []) if x["id"] == k), None)


def remind(uid, x, zone=None):
    """Sets the reminder of a card; returns the reminder."""
    now = datetime.datetime.now(zone or _zone(uid))
    item = profiles.add_reminder(uid, remind_text(x), remind_at(x, now) * 1000)
    try:
        import tagebuch
        tagebuch.note(uid, "erinnerung", item["text"], ref=item["id"])
    except Exception:
        pass
    return item


def _zone(uid):
    import chat
    return chat.user_zone(profiles.effective(uid).get("tz", ""))


def mark(uid, k, how, tell=True):
    """tell: the card of Offen (vorgaenge.py) follows; False when Offen itself pressed the button."""
    m = marks(uid)
    if how == "open":
        m.pop(k, None)
    else:
        m[k] = [how, int(time.time())]
    _save(uid, m)                       # the last reading leaves it out from now on (_last), „open“ brings it back
    _bump("markiert")
    if tell:
        import vorgaenge
        if how == "open":
            vorgaenge.reopen(uid, "fuerdich:" + k)
        else:
            vorgaenge.done(uid, "fuerdich:" + k, "erledigt" if how == "done" else "ausblenden")


CARD_BUDGET = 3.0              # seconds the card under Heute waits for a first reading
_tasks = {}                     # uid -> the reading that runs for the card


def _reading(uid, fresh=False):
    """The one reading that runs for this profile (tab, card under Heute), started if none runs."""
    t = _tasks.get(uid)
    if t is None or t.done():
        t = _tasks[uid] = asyncio.ensure_future(run(uid, fresh))
        t.add_done_callback(lambda f: f.cancelled() or f.exception())   # an error only shows as "not ready"
    return t


async def card(uid):
    """The card under Ich → Heute: reads (cache first) for at most CARD_BUDGET, then shows what is there."""
    if not mail.get(uid)["accounts"]:
        return {"ready": False, "nomail": True}
    t = _reading(uid)
    try:
        await asyncio.wait_for(asyncio.shield(t), CARD_BUDGET)
    except Exception:
        pass
    return heute(uid)


def heute(uid):
    """Numbers for the card under Ich → Heute: only from the last reading (never reads mail by itself)."""
    hit = _last(uid)
    if not hit:
        return {"ready": False}
    items = hit[1][0]
    return {"ready": True, "urgent": sum(1 for x in items if x["kind"] in URGENT),
            "total": len(items), "suspicious": sum(1 for x in items if x["kind"] == "verdacht")}


async def run(uid, fresh=False):
    """Reads the mailboxes off the event loop; one line in the journal for every outcome."""
    hit = _last(uid)
    cached = bool(hit and time.time() - hit[0] < CACHE_SECONDS and not fresh)
    t0 = time.time()
    try:
        items, errors = await vorrang.in_thread("Für dich", scan, uid, None, None, bool(fresh or (hit and not cached)))
    except notaus.NotausAktiv:
        print("fuerdich: gestoppt grund=notaus", flush=True)
        raise HTTPException(503, "Notaus: Postfach lesen ist gerade gestoppt.")
    if not cached:
        _bump("gelesen")
        _live(len(items))
        import vorgaenge   # what needs the person goes to Offen (in the list; Von selbst puts the card into the chat)
        vorgaenge.from_fuerdich(uid, items, datetime.datetime.now(_zone(uid)).date())
        print(f"fuerdich: gelesen funde={len(items)} fehler={len(errors)} sekunden={time.time() - t0:.1f}", flush=True)
    return items, errors


# ---------------------------------------------------------------- counts for Zustand → Live
def _bump(kind, n=1):
    with _lock:
        _day.bump(kind, n)


def today_counts():
    return _day.counts()


def for_live():
    """Live (node E-Mail): profiles with a kept reading in memory and mailboxes answered from it today; numbers only."""
    return {"profiles": sum(1 for d in _v.mem.values() if d.get("at")), "answers": _day.counts().get("vorrat", 0)}


def _live(n):
    try:
        import live
        live.event("Für dich", f"{n} Funde")
    except Exception:
        pass


async def view(prof, fresh=False):
    """The tab „Für dich“: the last reading at once (up to STALE_SECONDS old; an older one than CACHE_SECONDS is read
    anew behind it), the first one waited for at most VIEW_BUDGET, then {"loading": True} while it goes on."""
    uid, now = prof["id"], time.time()
    hit = _last(uid)                    # after a restart from the sealed file: the last reading at once
    if hit and not fresh and now - hit[0] < STALE_SECONDS:
        # at once with the last reading (Dominik 2026-10-19 „die fenster sollten direkt reagieren“); an older one is
        # read anew behind it and shows on the next look
        if now - hit[0] >= CACHE_SECONDS:
            _reading(uid)
        return dict(public(uid, *hit[1]), stand=int(hit[0]))
    t = _reading(uid, fresh)
    try:
        items, errors = await asyncio.wait_for(asyncio.shield(t), VIEW_BUDGET)
    except asyncio.TimeoutError:
        print(f"fuerdich: laedt noch {profiles.log_name(prof)}", flush=True)
        return {"items": [], "counts": {k: 0 for k in KINDS}, "errors": [], "loading": True}
    return dict(public(uid, items, errors), stand=int(time.time()))


# ---------------------------------------------------------------- endpoints
def _mine(request, prof, rate="fuerdich"):
    if not features.allowed("fuerdich", prof["id"]):
        raise HTTPException(403, features.missing_text("fuerdich", prof["id"]) or "„Für dich“ ist aus.")
    guard.limit(request, rate, prof["id"])


@router.get("/api/profile/fuerdich", dependencies=[Depends(assistant)])
async def api_get(request: Request, fresh: bool = False, prof=Depends(own_profile)):
    _mine(request, prof, "fuerdichlesen" if fresh else "fuerdich")
    if not mail.get(prof["id"])["accounts"]:
        print(f"fuerdich: kein postfach {profiles.log_name(prof)}", flush=True)
        return {"items": [], "counts": {k: 0 for k in KINDS}, "errors": [], "nomail": True}
    return await view(prof, fresh)


@router.post("/api/profile/fuerdich/mark", dependencies=[Depends(assistant)])
async def api_mark(request: Request, prof=Depends(own_profile)):
    _mine(request, prof)
    b = await json_body(request, 2 * 1024)
    k, how = b.get("id"), b.get("as")
    if not isinstance(k, str) or not re.fullmatch(r"[0-9a-f]{20}", k) or how not in ("done", "no", "open"):
        print("fuerdich: markieren abgelehnt grund=eingabe", flush=True)
        raise HTTPException(400, "id and as (done, no, open)")
    mark(prof["id"], k, how)
    print(f"fuerdich: markiert als={how} {profiles.log_name(prof)}", flush=True)
    return {"ok": True}


@router.delete("/api/profile/fuerdich", dependencies=[Depends(assistant)])
def api_forget(request: Request, prof=Depends(browser_profile)):
    guard.limit(request, "fuerdich", prof["id"])
    forget(prof["id"])
    print(f"fuerdich: geloescht {profiles.log_name(prof)}", flush=True)
    return {"ok": True}


@router.post("/api/profile/fuerdich/act", dependencies=[Depends(assistant)])
async def api_act(request: Request, prof=Depends(own_profile)):
    """A button of a card: {"id", "do": "remind"} sets its reminder, {"id", "do": "more"} (Mehr davon) makes the shop a
    confirmed interest (ichweiss.py), {"id", "do": "cancel"} returns the draft of a
    cancelling mail ({"to", "subject", "text"}, nothing is sent; the preview sheet of the mail page sends)."""
    _mine(request, prof)
    b = await json_body(request, 2 * 1024)
    k, do, uid = b.get("id"), b.get("do"), prof["id"]
    if not isinstance(k, str) or not re.fullmatch(r"[0-9a-f]{20}", k) or do not in ("remind", "cancel", "more"):
        print("fuerdich: knopf abgelehnt grund=eingabe", flush=True)
        raise HTTPException(400, "id and do (remind, cancel, more)")
    x = find(uid, k)
    if x is None or do not in acts(uid, x):
        print(f"fuerdich: knopf abgelehnt grund={'fehlt' if x is None else 'nicht_erlaubt'} {profiles.log_name(prof)}", flush=True)
        raise HTTPException(404 if x is None else 403, "Diese Karte gibt es nicht mehr. Bitte neu laden."
                            if x is None else "Für diese Karte gibt es diesen Knopf nicht.")
    _bump("knopf")
    if do == "remind":
        item = remind(uid, x)
        print(f"fuerdich: erinnerung gesetzt {profiles.log_name(prof)}", flush=True)
        return {"ok": True, "text": item["text"], "due": item["due"]}
    if do == "more":
        import ichweiss
        item = ichweiss.more(uid, x["who"])
        print(f"fuerdich: mehr davon {profiles.log_name(prof)}", flush=True)
        return {"ok": True, "name": item["name"]}
    print(f"fuerdich: kuendigung entworfen {profiles.log_name(prof)}", flush=True)
    return dict(cancel_draft(uid, x, datetime.date.today()), ok=True)


# ---------------------------------------------------------------- Von selbst melden (proactive.py, kind "fuerdich")
# „von selbst nur bei Fristen und Verdacht“ (2a): a bill or a cancelling deadline today or tomorrow, a suspected
# phishing mail; once per card (proactive keeps the said ids). A new mail (IMAP IDLE of the mail page) only makes the
# next check read anew: new_mail(uid).
_new = set()


def new_mail(uid):
    """Called when a new mail came in: the next check of Von selbst reads the mailboxes anew."""
    _new.add(uid)


# IMAP IDLE of the mail page (mailidle.py, chat.mail_idle): a new mail in a profile's inbox makes the next check read
# anew at once; with IDLE off the check still reads every FUER_EVERY seconds (proactive.check_fuerdich)
mailidle.on_new(new_mail)


def wants_fresh(uid):
    if uid in _new:
        _new.discard(uid)
        return True
    return False


def due_notes(uid, items, today):
    """[(id, why, sentence)] of the cards that may speak by themselves today, by fixed rules."""
    out = []
    soon = {today.isoformat(), (today + datetime.timedelta(days=1)).isoformat()}
    for x in items:
        title, line = sentence(x, today)
        if x["kind"] == "verdacht":
            out.append((x["id"], "Verdacht", f"{title}. {line}"))
        elif x["kind"] in ("rechnung", "vertrag") and deadline(x) in soon:
            out.append((x["id"], "Frist", f"{title}. {line}"))
    return out


# ---------------------------------------------------------------- the assistant's tools and the briefing (extras.py)
TOOL = {"type": "function", "function": {
    "name": "fuer_dich",
    "description": "What the user's own mailbox says needs them (Für dich): bills with the day they are due, contracts "
                   "that renew with the last day to cancel, offers that end, people waiting for an answer, suspected "
                   "phishing mails. Returns a numbered list of fixed sentences.",
    "parameters": {"type": "object", "properties": {}}}}
TOOL_DO = {"type": "function", "function": {
    "name": "fuer_dich_tun",
    "description": "Acts on one entry of the last fuer_dich list, only when the user says so for that entry: "
                   "done (erledigt), no (nicht interessant) or remind (eine Erinnerung am Tag vor der Frist).",
    "parameters": {"type": "object", "properties": {
        "number": {"type": "integer", "description": "the number of the entry in the last fuer_dich list"},
        "do": {"type": "string", "enum": ["done", "no", "remind"]}}, "required": ["number", "do"]}}}
HINT = ("Fragen wie „Was muss ich erledigen?“ oder „Was steht in Für dich?“ beantwortest du mit fuer_dich und liest "
        "die Sätze aus dem Ergebnis vor, ohne etwas dazuzuerfinden. fuer_dich_tun nur, wenn die Person für eine "
        "Nummer ausdrücklich erledigt, nicht interessant oder erinnern sagt.")
LIST_MAX = 8
TOOL_WAIT = 20                  # seconds the voice tool waits for a reading before it uses the last one
LIST_KEEP = 1800                # seconds a numbered list stays valid for fuer_dich_tun
_listed = {}                    # uid -> (time, [ids in the order said])


def usable(uid):
    return bool(features.allowed("fuerdich", uid) and mail.get(uid)["accounts"])


def offer(ctx):
    who = ctx.get("who")
    if not who or not ctx.get("own") or not ctx.get("private", True) or not usable(who["id"]):
        return None
    return {"tools": [TOOL, TOOL_DO], "hint": HINT, "mail": {"fuer_dich"}, "changes": {"fuer_dich_tun"},
            "filler": {"fuer_dich": ("Ich schaue, was in deinem Postfach auf dich wartet.",
                                     "Let me see what your mailbox has for you.")}}


def say_list(uid, items, errors, today):
    """The fixed sentences of the list for the assistant, numbered; keeps the order for fuer_dich_tun."""
    pub = public(uid, items, errors, today)["items"][:LIST_MAX]
    _listed[uid] = (time.time(), [x["id"] for x in pub])
    # a mailbox that did not answer, in fixed words: with its kept items „Stand hh:mm“, else „gerade nicht lesbar“
    note = "".join(f"\nPostfach {n}: " + (f"{e}." if "Stand" in e else "gerade nicht lesbar, seine Einträge fehlen.")
                   for n, e in errors)
    if not pub:
        return "Für dich: nichts, was dich gerade braucht." + note
    lines = [f"{i}. {x['title']}. {x['line']} (Mail von {x['who']} vom {day_word(x['sent'], today)}"
             + (f", Betreff „{x['subject']}“" if x["subject"] else "") + (f", Ordner {x['folder']}" if x["folder"] != "INBOX" else "")
             + ")" for i, x in enumerate(pub, 1)]
    more = len(items) - len(pub)
    return ("Für dich (feste Sätze aus den Mails; lies sie so vor, wie sie stehen, und ändere nicht, wer auf wen wartet; "
            "nenne zu einem Eintrag die Mail, aus der er kommt):\n" + "\n".join(lines)
            + (f"\nUnd {more} weitere unter E-Mail → Für dich." if more > 0 else "") + note)


async def tool(name, args, ctx):
    uid = ctx["who"]["id"]
    if name == "fuer_dich":
        try:
            items, errors = await asyncio.wait_for(asyncio.shield(_reading(uid)), TOOL_WAIT)
        except asyncio.TimeoutError:
            # still reading (the first reading of a big mailbox on the Pi takes longer): the last reading if there is
            # one, else „liest noch“, never „nicht erreichbar“ (Dominik 2026-10-20); the reading goes on behind it
            hit = _last(uid)
            if hit and time.time() - hit[0] < STALE_SECONDS:
                items, errors = hit[1]
                print("fuerdich: werkzeug liste aus letzter lesung", flush=True)
            else:
                print("fuerdich: werkzeug laedt noch", flush=True)
                return "Für dich: ich lese dein Postfach gerade noch, das dauert beim ersten Mal etwas. Sag, dass du gleich noch einmal fragen sollst."
        except Exception as e:
            if getattr(e, "status_code", 0) == 503:
                print("fuerdich: werkzeug gestoppt grund=notaus", flush=True)
                return "Notaus: Postfach lesen ist gerade gestoppt. Sag das so."
            print(f"fuerdich: werkzeug fehler={type(e).__name__}", flush=True)
            return "Postfach gerade nicht lesbar. Sag das so."
        print(f"fuerdich: werkzeug liste funde={len(items)}", flush=True)
        return mail._wrap(say_list(uid, items, errors, datetime.datetime.now(_zone(uid)).date()))
    n, do = args.get("number"), args.get("do")
    t, ids = _listed.get(uid, (0, []))
    if do not in ("done", "no", "remind") or not isinstance(n, int) or not 1 <= n <= len(ids) or time.time() - t > LIST_KEEP:
        print("fuerdich: werkzeug tun abgelehnt grund=eingabe", flush=True)
        return "Not done: first read the list with fuer_dich, then name one of its numbers."
    x = find(uid, ids[n - 1])
    if x is None:
        print("fuerdich: werkzeug tun abgelehnt grund=fehlt", flush=True)
        return "Not done: this entry is gone. Read the list again with fuer_dich."
    if do == "remind":
        if "remind" not in acts(uid, x):
            print("fuerdich: werkzeug tun abgelehnt grund=nicht_erlaubt", flush=True)
            return "Not done: this entry has no reminder."
        item = remind(uid, x)
        print("fuerdich: werkzeug erinnerung gesetzt", flush=True)
        when = datetime.datetime.fromtimestamp(item["due"] / 1000, _zone(uid)).strftime("%d.%m. %H:%M")
        return f"Reminder set: '{item['text']}' at {when}."
    mark(uid, x["id"], do)
    print(f"fuerdich: werkzeug markiert als={do}", flush=True)
    return f"Marked entry {n} as {'done' if do == 'done' else 'not interesting'}; it no longer shows in Für dich."


BRIEF_MAX = 3


async def briefing(uid, zone=None):
    """The part of the daily briefing: what needs the person, from the last reading (read if there is none yet)."""
    if not usable(uid):
        return ""
    try:
        items, errors = await asyncio.wait_for(asyncio.shield(_reading(uid)), 10)
    except Exception:
        print("fuerdich: briefing ohne lesung", flush=True)
        return ""
    today = datetime.datetime.now(zone).date() if zone else datetime.date.today()
    pub = [x for x in public(uid, items, errors, today)["items"] if x["urgent"]]
    print(f"fuerdich: briefing teile={min(len(pub), BRIEF_MAX)}", flush=True)
    if not pub:
        return ""
    lines = [f"{x['title']}. {x['line']}" for x in pub[:BRIEF_MAX]]
    if len(pub) > BRIEF_MAX:
        lines.append(f"Und {len(pub) - BRIEF_MAX} weitere unter E-Mail → Für dich.")
    return mail._wrap("Für dich (aus deinem Postfach):\n" + "\n".join(lines))
