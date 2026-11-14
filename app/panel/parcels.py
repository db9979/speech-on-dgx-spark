"""Parcels from the profile's own e-mail: shipping mails of DHL, Hermes, DPD, GLS, UPS and Amazon are
recognised by their sender, the status is taken from the mail's words ("kommt heute", "zugestellt",
"liegt in der Filiale"). Nothing asks the carriers; no model guesses. Off until the admin allows it
(chat.parcels, needs chat.mail) and a profile switches it on (setting par_on). Guests never.

Shop names and item titles come from the mails: they count as mail text, so after a parcel lookup
the answer cannot switch or change anything.

Sendungen über der Mail-Liste (pl_mail-Ideen 1, Dominik 2026-11-13 „1-7“; part of this function, no switch of its
own): strip() gives at most STRIP open parcels of the last reading (memory or the sealed Vorrat, never a mailbox while
the page waits; an old reading is renewed in the background, at most every RENEW seconds), the ones coming today
first. A link only to the carrier's own fixed tracking page (TRACK_URL) with the tracking number set in, never a link
from a mail. ✕ (hide) keeps a parcel away until it has a new state; the hidden keys stay in the sealed Vorrat.
"""
import datetime
import hashlib
import email
import email.policy
import imaplib
import re
import threading
import time

import mail
import features
import postfach
import profiles
import tidy
import vorrat
from vorrat import Vorrat

DAYS = 14
SCAN = 300
_cache = {}
# Vorrat je Profil (3b): the last reading sealed in the profile's folder, so the first question after a restart is
# answered at once (with „Stand“ when older); deleted with the last mailbox and after IDLE_DAYS without a reading
SUPPLY = Vorrat("pakete-vorrat.bin", idle_days=14, write_every=300)
CARRIERS = [("DHL", ("dhl.de", "dhl.com", "deutschepost.de", "dhl-news.de")),
            ("Hermes", ("hermesworld.com", "myhermes.de", "hermes-europe.de")),
            ("DPD", ("dpd.de", "dpd.com")), ("GLS", ("gls-group.eu", "gls-pakete.de", "gls-group.com")),
            ("UPS", ("ups.com",)), ("Amazon", ("amazon.de", "amazon.com"))]
# the carriers' own tracking pages; the number (TRACK, letters and digits only) is set in, nothing else from a mail
TRACK_URL = {"DHL": "https://www.dhl.de/de/privatkunden/pakete-empfangen/verfolgen.html?piececode=",
             "Hermes": "https://www.myhermes.de/empfangen/sendungsverfolgung/sendungsinformation#",
             "DPD": "https://tracking.dpd.de/status/de_DE/parcel/",
             "GLS": "https://gls-group.com/DE/de/paketverfolgung?match=",
             "UPS": "https://www.ups.com/track?loc=de_DE&tracknum="}
STRIP = 3          # parcels above the mail list
RENEW = 600        # seconds between background readings for the strip
HIDE_MAX = 50      # hidden parcels kept per profile
ORDER = {"today": 0, "pickup": 1, "date": 2, "shipped": 3, "delivered": 4}
_renew = {}        # uid -> time of the last background reading
_renew_lock = threading.Lock()
WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
MONTHS = {m: i + 1 for i, m in enumerate(["januar", "februar", "märz", "april", "mai", "juni", "juli", "august",
                                           "september", "oktober", "november", "dezember"])}
DELIVERED = re.compile(r"(?i)^\s*(zugestellt|geliefert|delivered)\s*:|wurde (erfolgreich )?zugestellt|ist zugestellt|zugestellt am|erfolgreich zugestellt|"
                       r"wurde geliefert|ist angekommen|abgegeben (bei|an)|\bdelivered\b")
PICKUP = re.compile(r"(?i)abholbereit|zur abholung|abholen|packstation|filiale|paketshop|paket-?shop|ready for pick")
TODAY = re.compile(r"(?i)heute (zugestellt|geliefert|zustell|bei dir|bei ihnen)|kommt heute|zustellung heute|"
                   r"wird heute|lieferung heute|heute zugestellt|arriv\w* today|out for delivery|in zustellung|zustellung läuft|"
                   r"(ist|sind|befindet sich) in der zustellung")
TOMORROW = re.compile(r"(?i)kommt morgen|morgen (zugestellt|geliefert|bei dir|bei ihnen)|zustellung morgen|"
                      r"arriv\w* tomorrow")
SHIPPED = re.compile(r"(?i)versandt|verschickt|unterwegs|auf dem weg|übergeben|verlässt|in transit|shipped|"
                     r"sendung angekündigt|wird bald|bestellung ist")
DATE = re.compile(r"(?i)(voraussichtlich|zustellung|lieferung|ankunft|lieferdatum|zugestellt am|kommt am)"
                  r"[^.\n]{0,40}?(\d{1,2})\.\s?(\d{1,2})\.(\d{2,4})?")
DATE_WORD = re.compile(r"(?i)(voraussichtlich|zustellung|lieferung|ankunft|kommt)[^.\n]{0,40}?(\d{1,2})\.\s?"
                       r"(januar|februar|märz|april|mai|juni|juli|august|september|oktober|november|dezember)")
TRACK = re.compile(r"(?i)(?:sendungsnummer|sendungs-nr\.?|paketnummer|tracking(?:nummer| number)?|trackingnummer)"
                   r"\W{0,3}([A-Z0-9]{8,30})|\b(1Z[0-9A-Z]{16})\b")
SHOP = re.compile(r"\bvon ([A-ZÄÖÜ0-9][\w&.\-]{1,24}(?: [A-ZÄÖÜ][\w&.\-]{1,20})?)(?= kommt| ist| wurde| wird|\s*$|[,!.:])")
# Amazon sends many mails; only these subjects are about a parcel
AMAZON = re.compile(r"(?i)versand|verschickt|unterwegs|zugestellt|zustellung|geliefert|lieferung|paket|abhol|"
                    r"kommt|ankunft|shipped|delivered|delivery|arriving|out for")
ITEM = re.compile(r"[„\"“']([^“”\"']{3,60})[“”\"']")


def admin_on():
    return features.admin_on("parcels")


def usable(uid):
    return bool(features.allowed("parcels", uid) and mail.get(uid)["accounts"])


def carrier(sender):
    m = re.search(r"@([\w.\-]+)", sender or "")
    dom = (m.group(1) if m else "").lower()
    return next((n for n, ds in CARRIERS if any(dom == d or dom.endswith("." + d) for d in ds)), "")


def forged(msg):
    """True when the mail server says the sender's domain did not send this mail (DMARC, or SPF and
    DKIM both failed): a fake "DHL" mail never becomes a parcel. The top Authentication-Results header
    is the one the own mail server added; without one nothing can be told."""
    try:
        ar = (msg.get_all("Authentication-Results") or [""])[0]
    except Exception:
        return False
    ar = str(ar).lower()
    if "dmarc=" in ar:
        return bool(re.search(r"dmarc=(fail|reject|quarantine)", ar))
    return bool(re.search(r"\bspf=(fail|softfail)", ar) and re.search(r"\bdkim=(fail|none|neutral)", ar))


def _when(text, sent):
    """The expected day the mail names, if any."""
    m = DATE.search(text)
    if m:
        y = int(m.group(4)) if m.group(4) else sent.year
        y = y + 2000 if y < 100 else y
        try:
            return datetime.date(y, int(m.group(3)), int(m.group(2)))
        except ValueError:
            pass
    m = DATE_WORD.search(text)
    if m:
        try:
            return datetime.date(sent.year, MONTHS[m.group(3).lower()], int(m.group(2)))
        except ValueError:
            pass
    return None


def _status(s, sent):
    if DELIVERED.search(s):
        return "delivered", _when(s, sent) or sent
    if PICKUP.search(s):
        return "pickup", None
    if TODAY.search(s):
        return "today", sent
    if TOMORROW.search(s):
        return "date", sent + datetime.timedelta(days=1)
    if _when(s, sent):
        return "date", _when(s, sent)
    if SHIPPED.search(s):
        return "shipped", None
    return "", None


def classify(sender, subject, text, sent):
    """{carrier, shop, item, status, day, sent, track} of one shipping mail, or None."""
    who = carrier(sender)
    if not who:
        return None
    s = f"{subject}\n{text}"
    if who == "Amazon" and not AMAZON.search(subject):
        return None   # order confirmations ("Bestellt: ..."), offers ...
    # the subject says the newest state ("In Zustellung: ..."); the body often lists all steps or the
    # pick-up options, so it only counts when the subject says nothing
    status, day = _status(subject, sent)
    if status == "shipped" and _when(s, sent):        # "Paket unterwegs" + "Zustellung am 11.03." in the body
        status, day = "date", _when(s, sent)
    elif not status:
        status, day = _status(s, sent)
    if not status:
        return None
    t = TRACK.search(s)
    shop = SHOP.search(subject)
    item = ITEM.search(subject)
    return {"carrier": who, "shop": (shop.group(1) if shop else ("Amazon" if who == "Amazon" else ""))[:30],
            "item": (item.group(1) if item else "")[:50], "status": status,
            "day": day.isoformat() if day else "", "sent": sent.isoformat(),
            "track": (t.group(1) or t.group(2)).upper() if t else ""}


NOT_READ = ("sent", "drafts", "trash", "junk", "all", "group")   # postfach.role: never read for parcels
MAX_BOXES = 60


def _boxes(b):
    """The inbox and every other folder except sent, drafts, trash, spam and Gmail's views (issue 1: a folder the Spark
    sorts into; issue 2: an own folder „Lieferungen“ filled by a rule of the mail program)."""
    rest = sorted((n for n in b.boxes if n.upper() != "INBOX" and postfach.role(b, n) not in NOT_READ), key=str.lower)
    return ["INBOX"] + rest[:MAX_BOXES - 1]


def _from_carrier():
    """IMAP search words: sent by one of the carriers (the server picks them, so many folders stay quick)."""
    doms = [d for _, ds in CARRIERS for d in ds]
    out = []
    for i, d in enumerate(doms):
        out += (["OR"] if i < len(doms) - 1 else []) + ["FROM", f'"{d}"']
    return out


def _scan_account(acct, days):
    out, hit = [], []
    with tidy.Box(acct) as b:           # no tidying state: nothing can be moved; select = EXAMINE
        for box in _boxes(b):
            try:
                _open(b, box)
            except ValueError:
                if box == "INBOX":
                    raise ValueError("the inbox could not be opened")
                continue
            heads = mail.head_rows(b.c, sorted(b.search("SINCE", mail._since(days), *_from_carrier()))[-SCAN:])
            hit += [(heads[u]["date"], box, u, heads[u]) for u in heads if carrier(heads[u]["from"])]
        hit.sort(key=lambda x: x[0], reverse=True)
        for box in dict.fromkeys(x[1] for x in hit[:40]):
            _open(b, box)
            for _, _, u, h in (x for x in hit[:40] if x[1] == box):
                msg = _body(b, u)
                if msg is None or forged(msg):
                    continue
                text, _ = mail.plain(msg)
                x = classify(h["from"], h["subject"], text[:3000], mail.local(h["date"]).date())
                if x:
                    x["at"] = h["date"].timestamp()
                    out.append(x)
    return out


def _open(b, box):
    """EXAMINE (read only). The inbox by its plain name like every other reader of it (mail._Session), the other
    folders by tidy.Box (quoted, modified UTF-7)."""
    if box != "INBOX":
        b.select(box)
        return
    typ, _ = b.c.select("INBOX", readonly=True)
    if typ != "OK":
        raise ValueError("the inbox could not be opened")


def _body(b, uid):
    typ, data = b.c.uid("FETCH", str(uid), f"(BODY.PEEK[]<0.{int(mail.MAX_FETCH)}>)")
    raw = next((p[1] for p in data if isinstance(p, tuple) and p[1]), None) if typ == "OK" else None
    return email.message_from_bytes(raw, policy=email.policy.default) if raw else None


def scan(uid, days=DAYS):
    """The profile's parcels, newest mail per parcel; [(mailbox, error)]. Kept in memory; taken from there while fresh
    enough (vorrat.DIENSTE "parcels"), an older reading when the mailbox is slow, saying so (vorrat.stand)."""
    if not mail.get(uid)["accounts"]:
        drop(uid)
        return [], []
    return vorrat.take_sync("parcels", _cache.get(uid) or _kept(uid), ("parcels", uid), lambda: _read(uid, days))


def _kept(uid):
    """The sealed reading of the profile ((time, (parcels, errors)) or None); it goes back into memory."""
    d = SUPPLY.load(uid)
    if not isinstance(d.get("t"), (int, float)) or not isinstance(d.get("v"), list):
        return None
    hit = _cache[uid] = (d["t"], (d["v"], []))
    return hit


def _read(uid, days):
    found, errors = [], []
    for a in mail.get(uid)["accounts"]:
        try:
            found += _scan_account(a, days)
        except (ValueError, OSError, imaplib.IMAP4.error) as e:
            errors.append((a.get("name", ""), str(e) if isinstance(e, ValueError) else type(e).__name__))
    found.sort(key=lambda x: x["at"], reverse=True)
    seen, out = set(), []
    for x in found:   # one entry per parcel: its tracking number, else carrier + shop + item
        key = x["track"] or (x["carrier"], x["shop"], x["item"])
        if key not in seen:
            seen.add(key)
            out.append(x)
    res = (out, errors)
    _cache[uid] = (time.time(), res)
    if not errors:   # only a complete reading is kept on the disk
        SUPPLY.load(uid).update(t=_cache[uid][0], v=out)
        SUPPLY.changed(uid)
    return res


def drop(uid):
    _cache.pop(uid, None)
    SUPPLY.forget(uid)


def _day_word(d, today):
    k = (d - today).days
    return "heute" if k == 0 else "morgen" if k == 1 else "gestern" if k == -1 else \
        f"am {WEEKDAYS[d.weekday()]}, {d.day}.{d.month}."


def _end(s):
    return s if s.endswith(".") else s + "."


def sentence(x, today):
    """'DHL-Paket von Zalando: kommt heute.' or None when it is old news."""
    what = f"{x['carrier']}-Paket" if x["carrier"] != "Amazon" else "Amazon-Lieferung"
    if x["shop"] and x["shop"] != x["carrier"]:
        what += f" von {x['shop']}"
    if x["item"]:
        what += f" („{x['item']}“)"
    day = datetime.date.fromisoformat(x["day"]) if x["day"] else None
    sent = datetime.date.fromisoformat(x["sent"])
    if x["status"] == "delivered":
        if day and (today - day).days > 2:
            return None
        return _end(f"{what}: wurde {_day_word(day, today)} zugestellt") if day else f"{what}: wurde zugestellt."
    if x["status"] == "pickup":
        return f"{what}: liegt zur Abholung bereit (Mail vom {sent.day}.{sent.month}.)."
    if day:
        if day < today:
            return f"{what}: sollte laut Mail {_day_word(day, today)} kommen, eine Zustellung ist noch nicht gemeldet."
        return _end(f"{what}: kommt {_day_word(day, today)}")
    if (today - sent).days > 10:
        return None
    return f"{what}: ist unterwegs (Mail vom {sent.day}.{sent.month}.)."


def report(uid, today=None):
    today = today or datetime.date.today()
    found, errors = scan(uid)
    lines = [s for s in (sentence(x, today) for x in found) if s]
    out = ("Pakete laut deinen Mails:\n" + "\n".join(lines)) if lines else \
        "In den Mails der letzten 14 Tage ist kein offenes Paket."
    out += "".join(f"\nPostfach '{n}' nicht lesbar: {e}" for n, e in errors)
    return mail._wrap(out)


def link(x):
    """The carrier's own tracking page for the parcel, or "" (Amazon, no number, or a number not plain)."""
    t = x.get("track") or ""
    return TRACK_URL[x["carrier"]] + t if x.get("carrier") in TRACK_URL and re.fullmatch(r"[A-Z0-9]{8,30}", t) else ""


def key(x):
    """A parcel in one state: a new state is a new key, so a hidden parcel comes back when something happens."""
    who = x.get("track") or f"{x.get('carrier')}|{x.get('shop')}|{x.get('item')}"
    return hashlib.sha256(f"{who}|{x.get('status')}|{x.get('day')}".encode()).hexdigest()[:16]


def _renew_soon(uid, now):
    """Reads the mailboxes in the background when the last reading is older than RENEW (never while the page waits)."""
    with _renew_lock:
        if now - _renew.get(uid, 0) < RENEW:
            return
        _renew[uid] = now

    def run():
        try:
            scan(uid)
        except Exception as e:
            print(f"mail: parcels strip not readable ({type(e).__name__}) | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    threading.Thread(target=run, daemon=True, name="pakete-streifen").start()


def strip(uid, today=None, now=None):
    """Sendungen über der Mail-Liste: [{key, satz, link}] of at most STRIP open parcels, today's first, from the last
    reading only; [] when the function is off for the profile."""
    if not usable(uid):
        return []
    today, now = today or datetime.date.today(), time.time() if now is None else now
    hit = _cache.get(uid) or _kept(uid)
    if not hit or now - hit[0] > RENEW:
        _renew_soon(uid, now)
    if not hit:
        return []
    hidden = set(SUPPLY.load(uid).get("weg") or [])
    out = []
    for x in sorted(hit[1][0], key=lambda x: ORDER.get(x.get("status"), 9)):
        s, k = sentence(x, today), key(x)
        if s and k not in hidden:
            out.append({"key": k, "satz": s, "link": link(x)})
    return out[:STRIP]


def heute_zahl(uid, today):
    """Natürliches Gespräch (gespraech.py): how many parcels come today after the last reading (memory or the sealed
    Vorrat), None without one. Never reads a mailbox for it."""
    if not usable(uid):
        return None
    hit = _cache.get(uid) or _kept(uid)
    if not hit:
        return None
    return sum(1 for x in hit[1][0] if x.get("status") == "today"
               or (x.get("status") == "date" and x.get("day") == today.isoformat()))


def hide(uid, k):
    """✕ on the strip: the parcel stays away until it has a new state (key)."""
    d = SUPPLY.load(uid)
    d["weg"] = ([x for x in d.get("weg") or [] if x != k] + [k])[-HIDE_MAX:]
    SUPPLY.changed(uid)


def today_lines(uid, today=None):
    """Fixed sentences of parcels that come today (for "Von selbst melden" and the briefing)."""
    today = today or datetime.date.today()
    found, _ = scan(uid)
    return [sentence(x, today) for x in found if x["status"] in ("today", "date") and x["day"] == today.isoformat()]


# ---------------------------------------------------------------- assistant tool
TOOL = {"type": "function", "function": {
    "name": "parcels",
    "description": "Parcels and deliveries according to the user's shipping e-mails (DHL, Hermes, DPD, GLS, UPS, "
                   "Amazon) of the last 14 days: what comes today, what is on its way, what was delivered.",
    "parameters": {"type": "object", "properties": {}}}}
HINT = ("Fragen zu Paketen und Lieferungen beantwortest du mit parcels. Lies die Sätze aus dem Ergebnis vor, "
        "ohne etwas dazuzuerfinden.")


def offer(ctx):
    who = ctx.get("who")
    if not who or not ctx.get("own") or not ctx.get("private", True) or not usable(who["id"]):
        return None
    return {"tools": [TOOL], "hint": HINT, "mail": {"parcels"},
            "filler": {"parcels": ("Ich schaue in deine Versandmails.", "Let me check your shipping mails.")}}


async def tool(name, args, ctx):
    import asyncio
    try:
        return await asyncio.to_thread(report, ctx["who"]["id"]) + vorrat.stand("parcels")
    except Exception as e:
        return f"Postfach nicht lesbar: {type(e).__name__}"


async def briefing(uid, zone=None):
    if not usable(uid):
        return ""
    import asyncio
    today = datetime.datetime.now(zone).date() if zone else datetime.date.today()
    try:
        lines = await asyncio.to_thread(today_lines, uid, today)
    except Exception:
        return ""
    return mail._wrap("Parcels today:\n" + "\n".join(lines)) if lines else ""


# ---------------------------------------------------------------- API ("Ich" → Pakete)
from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402

import guard  # noqa: E402
from core import assistant, json_body, own_profile  # noqa: E402

router = APIRouter()


@router.get("/api/profile/parcels", dependencies=[Depends(assistant)])
async def api_get(fresh: bool = False, prof=Depends(own_profile)):
    import asyncio
    on = features.allowed("parcels", prof["id"])
    if not admin_on():
        raise HTTPException(403, "parcels are turned off")
    if not on or not mail.get(prof["id"])["accounts"]:
        return {"on": on, "lines": [], "errors": []}
    if fresh:
        drop(prof["id"])
    found, errors = await asyncio.to_thread(scan, prof["id"])
    today = datetime.date.today()
    return {"on": on, "lines": [s for s in (sentence(x, today) for x in found) if s],
            "errors": [f"{n}: {e}" for n, e in errors]}


@router.post("/api/profile/parcels/hide", dependencies=[Depends(assistant)])
async def api_hide(request: Request, prof=Depends(own_profile)):
    """✕ on the strip above the mail list: {"key": 16 hex}."""
    guard.limit(request, "post", prof["id"])
    if not features.allowed("parcels", prof["id"]):
        print(f"mail: parcel hide refused, off | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(403, "parcels are turned off")
    b = await json_body(request, 1024)
    k = b.get("key")
    if not isinstance(k, str) or not re.fullmatch(r"[0-9a-f]{16}", k):
        print(f"mail: parcel hide refused, input | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(400, "key")
    hide(prof["id"], k)
    print(f"mail: parcel hidden | {profiles.log_name(prof)}", flush=True)
    return {"ok": True}
