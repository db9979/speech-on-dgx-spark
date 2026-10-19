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

Kept: the found items only in memory (CACHE_SECONDS); in users/<id>/fuerdich.json only what the person pressed
(erledigt / nicht interessant) as hashes of the Message-ID with the time, so a pressed card does not come back.

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
import notaus
import profiles
import vorrang
from common import DayCounter
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
STALE_SECONDS = 24 * 3600       # the tab shows an older reading at once and reads anew in the background
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
_cache = {}                     # uid -> (time, result)
_day = DayCounter()             # per day: runs, found, failed, marked (Zustand → Live)


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
    _cache.pop(uid, None)


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


def suspicious(sender, subject, text, link_domains, forged=False):
    """The brand a mail pretends to come from, when it does not; '' when it looks fine."""
    dom = domain(sender)
    name = email.utils.parseaddr(sender or "")[0].lower()
    head = f"{name} {subject}".lower()
    for brand, domains in BRANDS.items():
        if not re.search(r"\b" + re.escape(brand) + r"\b", head):
            continue
        if forged:
            return brand
        if _of(dom, domains):
            foreign = [d for d in link_domains if not _of(d, domains) and not _of(d, (dom,))]
            if foreign and ACTION.search(f"{subject}\n{text}") and len(foreign) == len(link_domains):
                return brand        # all links lead elsewhere and it asks to log in or confirm
            return ""
        if ACTION.search(f"{subject}\n{text}"):
            return brand
    return ""


def classify(h, text, sent, today, raw="", forged=False):
    """One item {kind, ...} of a mail or None. h: {"from", "subject", "bulk", "cat"} (cat: the tidy folder)."""
    frm, subj = h.get("from", ""), h.get("subject", "")
    s = f"{subj}\n{text[:6000]}"
    brand = suspicious(frm, subj, text, links(raw, text), forged)
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


def _account(acct, uid, today, now):
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
                    x = classify(h, text, sent, today, _raw_text(msg), parcels.forged(msg))
                if x:
                    x.update(id=key(h["mid"], acct["id"], n), who=who(h["from"]), subject=subj[:90],
                             sent=sent.isoformat(), at=int(sent_dt.timestamp()), ref=f"{acct['id']}:{n}")
                    out.append(x)
    print(f"fuerdich: postfach gelesen ordner={len(boxes)} mails={read} funde={len(out)}", flush=True)
    return out


def scan(uid, today=None, now=None, force=False):
    """(items newest first without pressed ones, [(mailbox name, error)]). force: read anew whatever the cache holds
    (the cache stays until the new reading replaces it, so the tab keeps showing the last one meanwhile)."""
    hit = _cache.get(uid)
    if hit and time.time() - hit[0] < CACHE_SECONDS and today is None and not force:
        return hit[1]
    today = today or datetime.date.today()
    now = now or datetime.datetime.now(datetime.timezone.utc)
    found, errors = [], []

    def one(a):
        try:
            return _account(a, uid, today, now), None
        except (ValueError, OSError, imaplib.IMAP4.error) as e:
            return [], (a.get("name", ""), "nicht_lesbar" if isinstance(e, ValueError) else type(e).__name__)
    accts = mail.get(uid)["accounts"]
    # all mailboxes at the same time (Dominik 2026-10-19 „dauert länger als sonst“), each its own IMAP session
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(accts))) as ex:
        for got, err in ex.map(one, accts):
            found += got
            if err:
                errors.append(err)
    pressed = marks(uid)
    seen, items = set(), []
    for x in sorted(found, key=lambda x: x["at"], reverse=True):
        if x["id"] in seen or x["id"] in pressed:
            continue
        seen.add(x["id"])
        items.append(x)
    offers = [x for x in items if x["kind"] == "angebot"][MAX_OFFERS:]
    items = [x for x in items if x not in offers][:MAX_ITEMS]
    res = (items, errors)
    if len(_cache) > 200:
        _cache.clear()
    _cache[uid] = (time.time(), res)
    return res


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
        return f"{w} wartet seit {x['days']} Tagen auf deine Antwort", "In der Mail steht eine Frage an dich."
    return w, ""


def public(uid, items, errors, today=None):
    today = today or datetime.date.today()
    out = []
    for x in items:
        title, line = sentence(x, today)
        out.append({"id": x["id"], "kind": x["kind"], "urgent": x["kind"] in URGENT, "title": title, "line": line,
                    "who": x.get("who", ""), "subject": x.get("subject", ""), "sent": x["sent"], "day": x.get("day", ""),
                    "amount": x.get("amount", "")})
    out.sort(key=lambda y: (not y["urgent"], y["day"] or "9999", y["sent"]))
    counts = {k: sum(1 for y in out if y["kind"] == k) for k in KINDS}
    return {"items": out, "counts": counts, "errors": [f"{n}: {e}" for n, e in errors]}


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
    """Numbers for the card under Ich → Heute: only from the cache (never reads mail by itself)."""
    hit = _cache.get(uid)
    if not hit:
        return {"ready": False}
    items = hit[1][0]
    return {"ready": True, "urgent": sum(1 for x in items if x["kind"] in URGENT),
            "total": len(items), "suspicious": sum(1 for x in items if x["kind"] == "verdacht")}


async def run(uid, fresh=False):
    """Reads the mailboxes off the event loop; one line in the journal for every outcome."""
    hit = _cache.get(uid)
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
        print(f"fuerdich: gelesen funde={len(items)} fehler={len(errors)} sekunden={time.time() - t0:.1f}", flush=True)
    return items, errors


# ---------------------------------------------------------------- counts for Zustand → Live
def _bump(kind, n=1):
    with _lock:
        _day.bump(kind, n)


def today_counts():
    return _day.counts()


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
    hit = _cache.get(uid)
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
    m = marks(prof["id"])
    if how == "open":
        m.pop(k, None)
    else:
        m[k] = [how, int(time.time())]
    _save(prof["id"], m)
    hit = _cache.get(prof["id"])
    if hit and how != "open":
        _cache[prof["id"]] = (hit[0], ([x for x in hit[1][0] if x["id"] != k], hit[1][1]))
    elif how == "open":
        _cache.pop(prof["id"], None)
    _bump("markiert")
    print(f"fuerdich: markiert als={how} {profiles.log_name(prof)}", flush=True)
    return {"ok": True}


@router.delete("/api/profile/fuerdich", dependencies=[Depends(assistant)])
def api_forget(request: Request, prof=Depends(browser_profile)):
    guard.limit(request, "fuerdich", prof["id"])
    forget(prof["id"])
    print(f"fuerdich: geloescht {profiles.log_name(prof)}", flush=True)
    return {"ok": True}
