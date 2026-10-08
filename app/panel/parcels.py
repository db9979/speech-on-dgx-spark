"""Parcels from the profile's own e-mail: shipping mails of DHL, Hermes, DPD, GLS, UPS and Amazon are
recognised by their sender, the status is taken from the mail's words ("kommt heute", "zugestellt",
"liegt in der Filiale"). Nothing asks the carriers; no model guesses. Off until the admin allows it
(chat.parcels, needs chat.mail) and a profile switches it on (setting par_on). Guests never.

Shop names and item titles come from the mails: they count as mail text, so after a parcel lookup
the answer cannot switch or change anything.
"""
import datetime
import imaplib
import re
import time

import mail
import profiles
from common import load_config

DAYS = 14
CACHE_SECONDS = 600
SCAN = 300
_cache = {}
CARRIERS = [("DHL", ("dhl.de", "dhl.com", "deutschepost.de", "dhl-news.de")),
            ("Hermes", ("hermesworld.com", "myhermes.de", "hermes-europe.de")),
            ("DPD", ("dpd.de", "dpd.com")), ("GLS", ("gls-group.eu", "gls-pakete.de", "gls-group.com")),
            ("UPS", ("ups.com",)), ("Amazon", ("amazon.de", "amazon.com"))]
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
    c = load_config().get("chat", {})
    return bool(c.get("mail", False) and c.get("parcels", False))


def usable(uid):
    return bool(uid and admin_on() and profiles.settings(uid).get("par_on") and mail.get(uid)["accounts"])


def carrier(sender):
    m = re.search(r"@([\w.\-]+)", sender or "")
    dom = (m.group(1) if m else "").lower()
    return next((n for n, ds in CARRIERS if any(dom == d or dom.endswith("." + d) for d in ds)), "")


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


def _scan_account(acct, days):
    out = []
    with mail._Session(acct) as s:
        uids = sorted(s.search("SINCE", mail._since(days)))[-SCAN:]
        heads = s.headers(uids)
        hit = [u for u, h in heads.items() if carrier(h["from"])]
        for u in sorted(hit, key=lambda u: heads[u]["date"], reverse=True)[:40]:
            msg = s.body(u)
            if msg is None:
                continue
            text, _ = mail.plain(msg)
            x = classify(heads[u]["from"], heads[u]["subject"], text[:3000], heads[u]["date"].date())
            if x:
                x["at"] = heads[u]["date"].timestamp()
                out.append(x)
    return out


def scan(uid, days=DAYS):
    """The profile's parcels, newest mail per parcel; [(mailbox, error)]."""
    hit = _cache.get(uid)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
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
    return res


def drop(uid):
    _cache.pop(uid, None)


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
        return await asyncio.to_thread(report, ctx["who"]["id"])
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
from fastapi import APIRouter, Depends, HTTPException  # noqa: E402

from core import assistant, own_profile  # noqa: E402

router = APIRouter()


@router.get("/api/profile/parcels", dependencies=[Depends(assistant)])
async def api_get(fresh: bool = False, prof=Depends(own_profile)):
    import asyncio
    on = bool(profiles.settings(prof["id"]).get("par_on"))
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
