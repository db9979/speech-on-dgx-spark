"""Was ich über dich weiß (plan persoenlicher-assistent/plan.md, Dominik 2026-10-18 „3a 4a 6a 7a“, stages 3 and 4): one
page under Ich that shows what the Spark knows about the person and lets it be corrected:

    Interessen       proposed with their evidence (orders, offers and newsletters of a shop in the mails, words in Reddit
                     und Feeds), counted only after „Stimmt“; „Nicht so“ is remembered; own words can be added
    Wiederkehrendes  bills of the same sender in three or more months, about the same day („um den 15.“), with
                     „Monatlich erinnern“ (a monthly reminder)
    Diese Woche      the weekly review: marked done, still open, deadlines of the next seven days (Von selbst: Sundays
                     at 18 o'clock, kind "rueckblick")
    Diesen Monat     the sum of bills and orders of this month from the checked amounts of Für dich (7a)
    Aus dem Netz     at most one tip a day for a confirmed interest that allows it (4a): a separate run that sends only
                     the interest word to the web search (SearXNG through chat.web_search), never mail text
    Gemerkt          the newest facts of the memory and the mail style, with the ways to their own pages

Fixed rules, the panel decides, no model. Part of „Für dich aus Mails“ (chat.mail_insight, off; needs chat.mail);
released for every profile the admin did not block, guests never. Kept in users/<id>/interessen.json: the confirmed and
refused interests (name, state, time, web tips on or off) and the last web tip; everything else is read when the page
asks and kept in memory only.

    GET    /api/profile/ichweiss                  the page
    POST   /api/profile/ichweiss/interest         {"name", "state": "yes" | "no" | "forget", "web": bool}
    POST   /api/profile/ichweiss/recurring        {"id"}: a monthly reminder for it
    DELETE /api/profile/ichweiss                  forget every interest and the web tip
"""
import asyncio
import datetime
import hashlib
import imaplib
import json
import os
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import fuerdich
import guard
import mail
import notaus
import profiles
import vorrang
from common import DayCounter, load_config
from core import assistant, browser_profile, json_body, own_profile

router = APIRouter()
NAME_MAX = 40                   # an interest is a short word or name
MAX_INTERESTS = 60
MAX_PROPOSALS = 8
SHOP_MIN = 2                    # mails of a shop (orders, offers, newsletters) before it is proposed
REC_DAYS = 200                  # days of headers read for Wiederkehrendes
REC_SCAN = 1500                 # newest headers per folder
REC_MONTHS = 3                  # bills of a sender in this many months make it recurring
REC_SPREAD = 6                  # their days of the month lie within this many days
REC_SECONDS = 24 * 3600         # Wiederkehrendes is read at most once a day
REMIND_HOUR = 9
WEEK_DAYS = 7
TIP_HOURS = (10, 19)            # the web tip is looked for in the day only, once a day
TIP_KEEP = 3 * 86400

_lock = threading.Lock()
_rec = {}                       # uid -> (time, [recurring])
_day = DayCounter(angesehen=0, bestaetigt=0, abgelehnt=0, erinnerung=0, netztipp=0)   # Zustand → Live, numbers only


def _file(uid):
    return profiles._path(uid, "interessen.json")


def norm(name):
    return re.sub(r"\s+", " ", str(name or "").strip().lower())[:NAME_MAX]


def clean(name):
    """An interest's name as the page shows it: one line, letters, digits, spaces and a few signs."""
    v = re.sub(r"[^\w .&+'-]", " ", str(name or ""))
    return re.sub(r"\s+", " ", v).strip()[:NAME_MAX]


def load(uid):
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    d = d if isinstance(d, dict) else {}
    items = {}
    for k, v in (d.get("items") or {}).items():
        if isinstance(v, dict) and v.get("state") in ("yes", "no") and isinstance(v.get("name"), str) and norm(k) == k:
            items[k] = {"name": clean(v["name"]) or k, "state": v["state"], "t": int(v.get("t") or 0),
                        "web": v.get("web") is True, "src": v.get("src") if v.get("src") in SOURCES else "hand"}
    tip = d.get("tip") if isinstance(d.get("tip"), dict) else None
    return {"items": items, "tip": tip}


def _save(uid, d):
    with _lock:
        if len(d["items"]) > MAX_INTERESTS:      # the oldest refusals go first
            keep = sorted(d["items"].items(), key=lambda kv: (kv[1]["state"] == "yes", kv[1]["t"]))[-MAX_INTERESTS:]
            d["items"] = dict(keep)
        profiles._write(_file(uid), d)


def count(uid):
    return len(load(uid)["items"])


def forget(uid):
    try:
        os.remove(_file(uid))
    except OSError:
        pass
    _rec.pop(uid, None)


features.OWN["ichweiss"] = (count, forget)
SOURCES = {"shop": ("Mails eines Shops", "Mails of a shop"), "feeds": ("Stichwort in Reddit und Feeds", "Keyword in Reddit and feeds"),
           "karte": ("„Mehr davon“ an einer Karte", "\"More of this\" on a card"), "hand": ("selbst eingetragen", "added by you")}


def usable(uid):
    return bool(features.allowed("ichweiss", uid) and mail.get(uid)["accounts"])


def confirmed(uid):
    return [v for v in load(uid)["items"].values() if v["state"] == "yes"]


def known(uid, who):
    """Said yes or no to already („Mehr davon“ is shown only for a shop not known yet)."""
    return norm(clean(who)) in load(uid)["items"]


def fits(uid, who):
    """The confirmed interest an offer of this sender fits, or "" (Für dich sorts and marks it)."""
    n = norm(who)
    return next((v["name"] for k, v in load(uid)["items"].items() if v["state"] == "yes" and k and (k == n or k in n)), "")


def set_state(uid, name, state, src="hand", web=None):
    """yes / no / forget one interest by its name; returns the item or None (forgotten)."""
    k, nm = norm(clean(name)), clean(name)
    if not k or len(k) < 2:
        raise ValueError("name")
    d = load(uid)
    if state == "forget":
        d["items"].pop(k, None)
        _save(uid, d)
        return None
    old = d["items"].get(k, {})
    d["items"][k] = {"name": old.get("name") or nm, "state": state, "t": int(time.time()),
                     "web": (old.get("web", False) if web is None else bool(web)) and state == "yes",
                     "src": src if src in SOURCES else "hand"}
    _save(uid, d)
    _day.bump("bestaetigt" if state == "yes" else "abgelehnt")
    return d["items"][k]


# ---------------------------------------------------------------- proposals (3a)
def proposals(uid):
    """[{"name", "src", "why"}]: shops with SHOP_MIN or more mails in the last reading of Für dich, words of Reddit und
    Feeds; without the ones already said yes or no to. Only counts as evidence, never a word of a mail."""
    d = load(uid)["items"]
    out = []
    for who, c in sorted(fuerdich.shops(uid).items(), key=lambda kv: -sum(kv[1].values())):
        if norm(who) in d or sum(c.values()) < SHOP_MIN:
            continue
        parts = [f"{n} {w}" for n, w in ((c.get("orders", 0), "Bestellung" if c.get("orders") == 1 else "Bestellungen"),
                                          (c.get("offers", 0), "Angebot" if c.get("offers") == 1 else "Angebote"),
                                          (c.get("news", 0), "Newsletter")) if n]
        out.append({"name": clean(who), "src": "shop", "why": ", ".join(parts) + f" in {fuerdich.DAYS} Tagen"})
    try:
        import feeds
        if features.allowed("feeds", uid):
            for w in feeds.get(uid).get("words", [])[:20]:
                if norm(w) not in d and clean(w):
                    out.append({"name": clean(w), "src": "feeds", "why": "Stichwort in Reddit und Feeds"})
    except Exception:
        pass
    seen, res = set(), []
    for x in out:
        if norm(x["name"]) not in seen:
            seen.add(norm(x["name"]))
            res.append(x)
    return res[:MAX_PROPOSALS]


# ---------------------------------------------------------------- Wiederkehrendes (6a)
def _rec_account(acct, uid):
    import tidy
    found = {}
    with tidy.Box(acct) as b:               # no tidying state: nothing can be changed
        boxes = ["INBOX"]
        try:
            f = tidy.folder_of(tidy.state(uid), "rechnungen")
            if f and b.name(f) in b.boxes:
                boxes.append(b.name(f))
        except Exception:
            pass
        for box in boxes:
            notaus.stop("gespraech")
            b.select(box)                   # EXAMINE
            uids = sorted(b.search("SINCE", tidy._since(REC_DAYS)))[-REC_SCAN:]
            for m in b.headers(uids, "FROM SUBJECT DATE").values():
                subj = mail._hdr(m.get("Subject", ""))
                if not fuerdich.BILL.search(subj):
                    continue
                frm = mail._addr(m.get("From", ""))
                dom = fuerdich.domain(frm)
                if dom:
                    d = mail.local(mail._date(m.get("Date"))).date()
                    found.setdefault(dom, {"who": fuerdich.who(frm), "days": set()})["days"].add(d)
    print(f"ichweiss: kopfzeilen gelesen ordner={len(boxes)} absender={len(found)}", flush=True)
    return found


def recurring_scan(uid):
    """[{"id", "who", "day", "months"}]: senders whose bills came in REC_MONTHS or more months, about the same day."""
    hit = _rec.get(uid)
    if hit and time.time() - hit[0] < REC_SECONDS:
        return hit[1]
    groups = {}
    for a in mail.get(uid)["accounts"]:
        try:
            for dom, g in _rec_account(a, uid).items():
                x = groups.setdefault(dom, {"who": g["who"], "days": set()})
                x["days"] |= g["days"]
        except (ValueError, OSError, imaplib.IMAP4.error) as e:
            print(f"ichweiss: wiederkehrend fehler={type(e).__name__}", flush=True)
    out = []
    for dom, g in groups.items():
        by_month = {}
        for d in sorted(g["days"]):
            by_month.setdefault((d.year, d.month), d.day)     # the first bill of a month
        days = sorted(by_month.values())
        if len(by_month) < REC_MONTHS or days[-1] - days[0] > REC_SPREAD:
            continue
        out.append({"id": hashlib.sha256(f"rec:{dom}".encode()).hexdigest()[:12], "who": g["who"],
                    "day": days[len(days) // 2], "months": len(by_month)})
    out.sort(key=lambda x: x["day"])
    if len(_rec) > 200:
        _rec.clear()
    _rec[uid] = (time.time(), out)
    print(f"ichweiss: wiederkehrend gelesen funde={len(out)}", flush=True)
    return out


def next_monthly(day, now):
    """The next time a monthly reminder for this day of the month rings (9 o'clock, at most the 28th)."""
    day = min(max(int(day), 1), 28)
    at = now.replace(day=day, hour=REMIND_HOUR, minute=0, second=0, microsecond=0)
    if at <= now:
        y, m = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
        at = at.replace(year=y, month=m)
    return at


def rec_text(x):
    return f"Rechnung {fuerdich._one(x['who'], 40)} kommt um den {x['day']}."


# ---------------------------------------------------------------- Diese Woche and Diesen Monat (stage 4)
def cents(amount):
    """84,20 € -> 8420; "" or anything else -> 0."""
    m = re.search(r"(\d{1,3}(?:\.\d{3})*|\d+),(\d{2})", str(amount or ""))
    return int(m.group(1).replace(".", "")) * 100 + int(m.group(2)) if m else 0


def euro(c):
    return f"{c // 100:,}".replace(",", ".") + f",{c % 100:02d} €"


def month_sum(items, today):
    """{"bills", "orders", "total", "n"} in cents from the checked amounts of this month's mails (7a); a bill that is
    debited counts too. Only what the last reading of Für dich holds."""
    ym = today.strftime("%Y-%m")
    out = {"bills": 0, "orders": 0, "n": 0}
    for x in items:
        if x["kind"] in ("rechnung", "bestellung") and str(x.get("sent", "")).startswith(ym) and cents(x.get("amount")):
            out["bills" if x["kind"] == "rechnung" else "orders"] += cents(x["amount"])
            out["n"] += 1
    out["total"] = out["bills"] + out["orders"]
    return out


def week(uid, items, today):
    """The weekly review: {"done", "open", "next": [(day, title)]} from the marks of the last seven days, the cards
    that need the person and the deadlines of the next seven days."""
    since = time.time() - WEEK_DAYS * 86400
    done = sum(1 for v in fuerdich.marks(uid).values() if v[0] == "done" and v[1] >= since)
    soon = [(fuerdich.deadline(x), fuerdich.sentence(x, today)[0]) for x in items if fuerdich.deadline(x)]
    end = (today + datetime.timedelta(days=WEEK_DAYS)).isoformat()
    nxt = sorted((d, t) for d, t in soon if today.isoformat() <= d <= end)
    return {"done": done, "open": sum(1 for x in items if x["kind"] in fuerdich.URGENT), "next": nxt[:5]}


def week_sentence(w, today):
    head = f"Deine Woche: {w['done']} erledigt, {w['open']} offen."
    if not w["next"]:
        return head + " Nächste Woche keine Fristen aus deinen Mails."
    return head + " Nächste Woche: " + "; ".join(f"{fuerdich.day_word(d, today)} {t}" for d, t in w["next"][:3]) + "."


# ---------------------------------------------------------------- Aus dem Netz (4a)
def tip_of(uid):
    """The last web tip while it is fresh ({"name", "title", "url", "domain", "day"}), else None."""
    t = load(uid)["tip"]
    if not t or time.time() - int(t.get("t") or 0) > TIP_KEEP:
        return None
    return {k: t.get(k, "") for k in ("name", "title", "url", "domain", "day")}


def _ccfg():
    return load_config().get("chat", {})


def tip_allowed(uid):
    """The web tip needs the web search released for this profile and an address of the search (SearXNG)."""
    return bool(features.allowed("ichweiss", uid) and features.allowed("search", uid)
                and str(_ccfg().get("search_url") or "").strip())


def _tip_word(uid, today):
    web = sorted((v for v in load(uid)["items"].values() if v["state"] == "yes" and v["web"]), key=lambda v: v["name"])
    return web[today.toordinal() % len(web)]["name"] if web else ""


def _safe_url(u):
    u = str(u or "").strip()
    if not re.fullmatch(r"https://[A-Za-z0-9.\-]{3,253}(?::\d{1,5})?(?:/[^\s<>\"']{0,500})?", u):
        return "", ""
    return u, u.split("/")[2].split(":")[0].lower()


async def tip_run(uid, now):
    """At most once a day: one search with only the interest word (never mail text, never more than the word); the
    first result with a safe https address becomes the tip. Returns the tip or None."""
    import chat
    import httpx
    d = load(uid)
    day = now.date().isoformat()
    if (d["tip"] or {}).get("day") == day:
        return None
    word = _tip_word(uid, now.date())
    if not word:
        return None
    cc = _ccfg()
    d["tip"] = {"day": day, "t": int(time.time()), "name": word, "title": "", "url": "", "domain": ""}
    _save(uid, d)                        # tried today, whatever comes back
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=5)) as c:
            _, sources = await chat.web_search(c, dict(cc, search_pages=0, search_results=5), word)
    except Exception as e:
        print(f"ichweiss: netztipp fehler={type(e).__name__}", flush=True)
        return None
    for s in sources:
        url, dom = _safe_url(s.get("url"))
        if url:
            d = load(uid)
            d["tip"] = dict(d["tip"] or {}, title=fuerdich._one(s.get("title") or dom, 120), url=url, domain=dom)
            _save(uid, d)
            _day.bump("netztipp")
            _live("Netz-Tipp gefunden")
            print("ichweiss: netztipp gefunden", flush=True)
            return tip_of(uid)
    print("ichweiss: netztipp ohne treffer", flush=True)
    return None


async def due_once(now=None):
    """Called once a minute (extras.due_once): the web tip of the day for every profile that allows it."""
    import chat
    for uid in profiles.user_ids():
        if not tip_allowed(uid) or notaus.refuse("auto", uid):
            continue
        local = now.astimezone(chat.user_zone(profiles.effective(uid).get("tz", ""))) if now else \
            datetime.datetime.now(chat.user_zone(profiles.effective(uid).get("tz", "")))
        if not TIP_HOURS[0] <= local.hour < TIP_HOURS[1] or (load(uid)["tip"] or {}).get("day") == local.date().isoformat():
            continue
        try:
            await vorrang.quiet("Netz-Tipp")
            await tip_run(uid, local)
        except Exception as e:
            print(f"ichweiss: netztipp fehler={type(e).__name__}", flush=True)


# ---------------------------------------------------------------- the page
VIEW_BUDGET = 6.0
_tasks = {}


def _rec_reading(uid):
    t = _tasks.get(uid)
    if t is None or t.done():
        t = _tasks[uid] = asyncio.ensure_future(vorrang.in_thread("Für dich", recurring_scan, uid))
        t.add_done_callback(lambda f: f.cancelled() or f.exception())
    return t


async def view(prof):
    uid = prof["id"]
    import chat
    zone = chat.user_zone(profiles.effective(uid).get("tz", ""))
    today = datetime.datetime.now(zone).date()
    loading = []
    try:
        items, _ = await asyncio.wait_for(asyncio.shield(fuerdich._reading(uid)), VIEW_BUDGET) if mail.get(uid)["accounts"] else ([], [])
    except Exception:
        items = []
        loading.append("fuerdich")
    rec = []
    if mail.get(uid)["accounts"]:
        hit = _rec.get(uid)
        if hit:
            rec = hit[1]
            if time.time() - hit[0] >= REC_SECONDS:
                _rec_reading(uid)
        else:
            try:
                rec = await asyncio.wait_for(asyncio.shield(_rec_reading(uid)), VIEW_BUDGET)
            except Exception:
                loading.append("wiederkehrend")
    texts = {x["text"] for x in profiles.reminders(uid)}
    d = load(uid)
    w = week(uid, items, today)
    m = month_sum(items, today)
    facts = profiles.memory(uid)
    style = {}
    if features.allowed("mailstil", uid):
        import mailstil
        s = mailstil.public(uid)
        style = {"mails": s["mails"], "learned": s["learned"]}
    return {"interests": sorted(({"name": v["name"], "state": v["state"], "web": v["web"], "src": v["src"], "t": v["t"]}
                                 for v in d["items"].values()), key=lambda v: (v["state"] != "yes", v["name"].lower())),
            "proposals": proposals(uid), "sources": SOURCES,
            "recurring": [dict(x, set=rec_text(x) in texts) for x in rec],
            "week": dict(w, sentence=week_sentence(w, today)),
            "month": dict(m, line=month_line(m)),
            "tip": tip_of(uid), "tips": tip_allowed(uid),
            "facts": {"count": len(facts), "items": [str(x.get("text", ""))[:200] for x in facts[-5:]][::-1]},
            "style": style, "loading": loading}


def month_line(m):
    if not m["n"]:
        return "Diesen Monat noch keine Beträge aus deinen Mails."
    return (f"Diesen Monat aus Mails: {euro(m['total'])} (Rechnungen {euro(m['bills'])}, Bestellungen {euro(m['orders'])}), "
            f"aus {m['n']} Mails.")


# ---------------------------------------------------------------- endpoints
def _mine(request, prof):
    if not features.allowed("ichweiss", prof["id"]):
        raise HTTPException(403, features.missing_text("ichweiss", prof["id"]) or "„Was ich über dich weiß“ ist aus.")
    guard.limit(request, "fuerdich", prof["id"])


@router.get("/api/profile/ichweiss", dependencies=[Depends(assistant)])
async def api_get(request: Request, prof=Depends(own_profile)):
    _mine(request, prof)
    out = await view(prof)
    _day.bump("angesehen")
    print(f"ichweiss: angesehen vorschlaege={len(out['proposals'])} interessen={len(out['interests'])} "
          f"wiederkehrend={len(out['recurring'])} {profiles.log_name(prof)}", flush=True)
    return out


@router.post("/api/profile/ichweiss/interest", dependencies=[Depends(assistant)])
async def api_interest(request: Request, prof=Depends(own_profile)):
    _mine(request, prof)
    b = await json_body(request, 2 * 1024)
    name, state, src, web = b.get("name"), b.get("state"), b.get("src", "hand"), b.get("web")
    if not isinstance(name, str) or state not in ("yes", "no", "forget") or (web is not None and not isinstance(web, bool)) \
            or src not in SOURCES:
        print("ichweiss: interesse abgelehnt grund=eingabe", flush=True)
        raise HTTPException(400, "name, state (yes, no, forget), web (true/false)")
    try:
        item = set_state(prof["id"], name, state, src, web)
    except ValueError:
        print("ichweiss: interesse abgelehnt grund=name", flush=True)
        raise HTTPException(400, "Ein Interesse braucht mindestens zwei Zeichen.")
    print(f"ichweiss: interesse als={state} {profiles.log_name(prof)}", flush=True)
    return {"ok": True, "item": item}


@router.post("/api/profile/ichweiss/recurring", dependencies=[Depends(assistant)])
async def api_recurring(request: Request, prof=Depends(own_profile)):
    _mine(request, prof)
    b = await json_body(request, 1024)
    rid, uid = b.get("id"), prof["id"]
    x = next((r for r in (_rec.get(uid) or (0, []))[1] if r["id"] == rid), None) if isinstance(rid, str) else None
    if x is None:
        print(f"ichweiss: erinnerung abgelehnt grund=fehlt {profiles.log_name(prof)}", flush=True)
        raise HTTPException(404, "Das gibt es nicht mehr. Bitte neu laden.")
    if not features.allowed("reminders", uid):
        print(f"ichweiss: erinnerung abgelehnt grund=aus {profiles.log_name(prof)}", flush=True)
        raise HTTPException(403, features.missing_text("reminders", uid) or "Timer und Erinnerungen sind aus.")
    if rec_text(x) in {r["text"] for r in profiles.reminders(uid)}:
        print(f"ichweiss: erinnerung schon da {profiles.log_name(prof)}", flush=True)
        return {"ok": True, "again": True}
    import chat
    now = datetime.datetime.now(chat.user_zone(profiles.effective(uid).get("tz", "")))
    item = profiles.add_reminder(uid, rec_text(x), int(next_monthly(x["day"], now).timestamp() * 1000), "monthly")
    _day.bump("erinnerung")
    print(f"ichweiss: erinnerung monatlich gesetzt {profiles.log_name(prof)}", flush=True)
    return {"ok": True, "text": item["text"], "due": item["due"]}


@router.delete("/api/profile/ichweiss", dependencies=[Depends(assistant)])
def api_forget(request: Request, prof=Depends(browser_profile)):
    _mine(request, prof)
    forget(prof["id"])
    print(f"ichweiss: geloescht {profiles.log_name(prof)}", flush=True)
    return {"ok": True}


def today_counts():
    return _day.counts()


def _live(what):
    try:
        import live
        live.event("Was ich über dich weiß", what)
    except Exception:
        pass
