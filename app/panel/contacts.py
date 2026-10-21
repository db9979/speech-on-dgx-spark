"""Contacts per profile, read only (CardDAV: iCloud, Nextcloud, others). Off until the admin allows it
(chat.contacts) and a profile switches it on for itself (setting con_on) and connects an address
book. Guests never.

    USERS_DIR/<user id>/contacts.json  {"accounts": [{id, name, url, user, password}],
                                        "cache": <sealed JSON list of contacts>, "fetched", "errors"}

The cards are fetched once a day (and on "Jetzt abholen") and kept encrypted. Names, numbers and
notes come from other people: they count as outside text, so after a lookup nothing in that answer
switches or changes anything.
"""
import datetime
import difflib
import hashlib
import json
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

import httpx

import hintergrund
import kontaktkarte
import netguard
import profiles
import vault
import features

MAX_ACCOUNTS = 4
MAX_CONTACTS = 5000
REFRESH = 24 * 3600
NS = {"d": "DAV:", "a": "urn:ietf:params:xml:ns:carddav"}
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember"]
_lock = threading.Lock()
_mem = {}   # uid -> (fetched, contacts): the opened cache


def admin_on():
    return features.admin_on("contacts")


def _file(uid):
    return profiles._path(uid, "contacts.json")


def _raw(uid):
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def accounts(uid):
    return [dict(x, password=vault.open_(x.get("password", ""))) for x in _raw(uid).get("accounts") or []
            if isinstance(x, dict) and x.get("url")]


def _save(uid, accts=None, cards=None, errors=None, books=None, spark=None):
    with _lock:
        d = _raw(uid)
        if books is not None:
            d["books"] = books
        if spark is not None:   # the Spark's own address book (Apple-Stil „6a“): only on the Spark, sealed
            d["spark"] = vault.seal(json.dumps(spark, ensure_ascii=False))
            _mem.pop(uid, None)
        if accts is not None:
            d["accounts"] = [dict(x, password=vault.seal(x.get("password", ""))) for x in accts]
        if cards is not None:
            d["cache"] = vault.seal(json.dumps(cards, ensure_ascii=False))
            d["fetched"] = int(time.time())
            _mem.pop(uid, None)
        if errors is not None:
            d["errors"] = errors
        profiles._write(_file(uid), d)


def cards(uid):
    """Every card of the profile: its address books' copy and the Spark's own address book."""
    d = _raw(uid)
    hit = _mem.get(uid)
    if hit and hit[0] == (d.get("fetched"), d.get("spark")):
        return hit[1]
    try:
        out = json.loads(vault.open_(d.get("cache", "")) or "[]")
    except ValueError:
        out = []
    out = out + [dict(x, book=SPARK) for x in _spark(d)]
    _mem[uid] = ((d.get("fetched"), d.get("spark")), out)
    return out


SPARK = "spark"   # the book id of the Spark's own address book


def _spark(d):
    """[card with "vcf"] of the Spark's own address book."""
    try:
        out = json.loads(vault.open_(d.get("spark", "")) or "[]")
    except ValueError:
        out = []
    return out if isinstance(out, list) else []


def usable(uid):
    return bool(features.allowed("contacts", uid) and (accounts(uid) or _spark(_raw(uid))))


def public(uid):
    d = _raw(uid)
    return {"accounts": [{"id": x["id"], "name": x.get("name", ""), "url": x["url"], "user": x.get("user", "")}
                         for x in accounts(uid)],
            "count": len(cards(uid)), "fetched": d.get("fetched"), "errors": d.get("errors") or [],
            "on": features.allowed("contacts", uid)}


def entry(body):
    url = str(body.get("url", "")).strip()
    if not re.fullmatch(r"https?://[^\s]{3,500}", url, re.I):
        raise ValueError("Die Adresse muss mit https:// beginnen")
    name = str(body.get("name", "")).strip()[:60] or (re.match(r"\w+://([^/:]+)", url).group(1))
    pw = body.get("password")
    return {"id": "k" + os.urandom(4).hex(), "name": name, "url": url, "user": str(body.get("user", "")).strip()[:200],
            "password": pw[:500] if isinstance(pw, str) else ""}


def remove(uid, aid):
    rest = [x for x in accounts(uid) if x["id"] != aid]
    _save(uid, rest, [] if not rest else None, books=[b for b in _raw(uid).get("books") or [] if b.get("acc") != aid])
    return public(uid)


def forget(uid):
    with _lock:
        try:
            os.remove(_file(uid))
        except OSError:
            pass
        _mem.pop(uid, None)


# ---------------------------------------------------------------- vCard
def _unfold(text):
    return re.sub(r"\r?\n[ \t]", "", text.replace("\r\n", "\n"))


def _val(v):
    return re.sub(r"\\([,;\\])", r"\1", v.replace("\\n", " ").replace("\\N", " ")).strip()


def parse_vcard(text):
    """{"name", "nick", "org", "phones": [(kind, number)], "emails": [...], "bday": "YYYY-MM-DD" or "--MM-DD"}; for the
    page Kontakte (Apple-Stil „6a“) also "given", "family", "title", "addrs" [{kind, street, zip, city, country}],
    "urls", "note" and "uid"."""
    c = {"name": "", "nick": "", "org": "", "phones": [], "emails": [], "bday": "", "given": "", "family": "", "title": "",
         "addrs": [], "urls": [], "note": "", "uid": ""}
    n = ""
    for line in _unfold(text).split("\n"):
        if ":" not in line:
            continue
        head, _, value = line.partition(":")
        key, *params = head.split(";")
        key = key.split(".")[-1].upper()   # item1.TEL → TEL
        ptxt = ";".join(params).lower()
        if key == "FN":
            c["name"] = _val(value)[:100]
        elif key == "N":
            f = [_val(x) for x in value.split(";")]
            n = " ".join(x for x in (f[1] if len(f) > 1 else "", f[0]) if x)
            c["family"], c["given"] = f[0][:80], (f[1] if len(f) > 1 else "")[:80]
        elif key == "NICKNAME":
            c["nick"] = _val(value)[:60]
        elif key == "ORG":
            c["org"] = _val(value.split(";")[0])[:80]
        elif key == "TITLE":
            c["title"] = _val(value)[:120]
        elif key == "UID":
            c["uid"] = value.strip()[:200]
        elif key == "NOTE":
            c["note"] = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", re.sub(r"\\([,;\\])", r"\1", value.replace("\\n", "\n")
                                                                         .replace("\\N", "\n")))[:2000].strip()
        elif key == "URL" and len(c["urls"]) < kontaktkarte.URLS_MAX:
            u = value.strip()[:300]
            if re.fullmatch(r"https?://[^\s<>\"]+", u):
                c["urls"].append(u)
        elif key == "ADR" and len(c["addrs"]) < kontaktkarte.ADDRS_MAX:
            f = [_val(x)[:120] for x in (value.split(";") + [""] * 7)[:7]]
            if any(f[2:]):
                c["addrs"].append({"kind": "Arbeit" if "work" in ptxt else "Privat" if "home" in ptxt else "Adresse",
                                   "street": f[2], "zip": f[5], "city": f[3], "country": f[6]})
        elif key == "TEL" and len(c["phones"]) < kontaktkarte.PHONES_MAX:
            kind = "Handy" if "cell" in ptxt or "iphone" in ptxt or "mobile" in ptxt else \
                "Arbeit" if "work" in ptxt else "Privat" if "home" in ptxt else "Telefon"
            num = re.sub(r"[^\d+ /()\-]", "", value.replace("tel:", ""))[:30].strip()
            if num:
                c["phones"].append([kind, num])
        elif key == "EMAIL" and len(c["emails"]) < kontaktkarte.MAILS_MAX:
            e = value.strip()[:120]
            if "@" in e:
                c["emails"].append(e.lower())
        elif key == "BDAY":
            v = value.strip()
            m = re.fullmatch(r"(\d{4}|--)-?(\d\d)-?(\d\d)(T.*)?", v)
            if m:
                year = m.group(1) if m.group(1) != "--" and m.group(1) not in ("1604", "0000") else "--"
                c["bday"] = (year if year != "--" else "-") + f"-{m.group(2)}-{m.group(3)}"
    c["name"] = c["name"] or n or c["org"]
    return c if c["name"] else None


# ---------------------------------------------------------------- CardDAV
def _xml(b):
    try:
        return ET.fromstring(b)
    except ET.ParseError:
        return None


async def _propfind(c, url, body, depth):
    r = await c.request("PROPFIND", url, content=body, headers={"Depth": str(depth), "Content-Type": "application/xml"})
    if r.status_code == 401:
        raise ValueError("Benutzername oder Passwort falsch (401)")
    return _xml(r.content) if r.status_code == 207 else None


async def _books(c, url):
    q = ('<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:a="urn:ietf:params:xml:ns:carddav"><d:prop>'
         '<d:resourcetype/><d:displayname/><d:current-user-principal/><a:addressbook-home-set/></d:prop></d:propfind>')
    names = {}
    seen, todo, out = set(), [url], []
    for _ in range(4):   # address -> principal -> home -> address books
        nxt = []
        for u in todo:
            if u in seen:
                continue
            seen.add(u)
            root = await _propfind(c, u, q, 1)
            if root is None:
                root = await _propfind(c, u, q, 0)
            if root is None and u == url:
                root = await _propfind(c, urljoin(u, "/.well-known/carddav"), q, 0)
            if root is None:
                continue
            for resp in root.findall("d:response", NS):
                el = resp.find("d:href", NS)
                href = urljoin(u, el.text.strip()) if el is not None and el.text else None
                prop = resp.find("d:propstat/d:prop", NS)
                if prop is None or not href:
                    continue
                if prop.find("d:resourcetype/a:addressbook", NS) is not None:
                    if href not in out:
                        out.append(href)
                        dn = prop.find("d:displayname", NS)
                        names[href] = re.sub(r"[\x00-\x1f\x7f]", "", dn.text or "").strip()[:60] if dn is not None and dn.text else ""
                    continue
                for tag in ("a:addressbook-home-set/d:href", "d:current-user-principal/d:href"):
                    h = prop.find(tag, NS)
                    if h is not None and h.text:
                        h = urljoin(u, h.text.strip())
                        if h not in seen:
                            nxt.append(h)
        if out or not nxt:
            break
        todo = nxt
    return [(h, names.get(h, "")) for h in out]


def _parts(root, base):
    """[(href, etag, vCard text)] of a multistatus answer."""
    out = []
    for resp in root.findall("d:response", NS) if root is not None else []:
        h = resp.find("d:href", NS)
        data = resp.find(".//a:address-data", NS)
        if h is None or not h.text or data is None or not data.text or "BEGIN:VCARD" not in data.text:
            continue
        tag = resp.find(".//d:getetag", NS)
        out.append((urljoin(base, h.text.strip()), (tag.text or "").strip() if tag is not None else "", data.text))
    return out


async def _cards(c, book):
    """[(href, etag, vCard text)] of one address book: addressbook-query, else list + multiget."""
    q = ('<?xml version="1.0"?><a:addressbook-query xmlns:d="DAV:" xmlns:a="urn:ietf:params:xml:ns:carddav">'
         '<d:prop><d:getetag/><a:address-data/></d:prop></a:addressbook-query>')
    r = await c.request("REPORT", book, content=q, headers={"Depth": "1", "Content-Type": "application/xml"})
    texts = _parts(_xml(r.content) if r.status_code == 207 else None, book)
    if texts:
        return texts
    root = await _propfind(c, book, '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:getetag/></d:prop></d:propfind>', 1)
    hrefs = [h.text.strip() for h in (root.iter("{DAV:}href") if root is not None else []) if h.text]
    hrefs = [h for h in hrefs if urljoin(book, h).rstrip("/") != book.rstrip("/")][:MAX_CONTACTS]
    for i in range(0, len(hrefs), 200):
        body = ('<?xml version="1.0"?><a:addressbook-multiget xmlns:d="DAV:" xmlns:a="urn:ietf:params:xml:ns:carddav">'
                '<d:prop><d:getetag/><a:address-data/></d:prop>' + "".join(f"<d:href>{h}</d:href>" for h in hrefs[i:i + 200])
                + "</a:addressbook-multiget>")
        r = await c.request("REPORT", book, content=body, headers={"Depth": "1", "Content-Type": "application/xml"})
        texts += _parts(_xml(r.content) if r.status_code == 207 else None, book)
    return texts


def _client(acct, seen=True):
    auth = (acct["user"], acct.get("password", "")) if acct.get("user") else None
    return netguard.client(netguard.USER, origin=acct["url"], timeout=httpx.Timeout(30, connect=8), auth=auth,
                           follow_redirects=True, headers={"User-Agent": "speech-on-dgx-spark"},
                           seen=hintergrund.tracker("contacts", acct.get("id")) if seen and acct.get("id") else None)


def _bid(aid, href):
    return "b" + hashlib.sha1(f"{aid}|{href}".encode()).hexdigest()[:10]


def _cid(aid, href):
    return "c" + hashlib.sha1(f"{aid}|{href}".encode()).hexdigest()[:12]


async def fetch_account(acct, books_out=None):
    """The cards of every address book of one account; each with its place (book, href, etag) for the page Kontakte.
    books_out gets [{id, acc, href, name}]."""
    async with _client(acct) as c:
        books = await _books(c, acct["url"])
        if not books:
            raise ValueError("kein Adressbuch unter dieser Adresse gefunden")
        out = []
        for href, name in books[:10]:
            bid = _bid(acct.get("id", ""), href)
            if books_out is not None:
                books_out.append({"id": bid, "acc": acct.get("id", ""), "href": href, "name": name})
            for ohref, etag, t in await _cards(c, href):
                parts = re.findall(r"BEGIN:VCARD.*?END:VCARD", t, re.S)
                for part in parts:
                    x = parse_vcard(part)
                    if x:
                        if len(parts) == 1:   # one card per object: the page may change it there
                            x.update(id=_cid(acct.get("id", ""), ohref), book=bid, href=ohref, etag=etag)
                        out.append(x)
        return out[:MAX_CONTACTS]


async def refresh(uid):
    """Fetches every address book of the profile; keeps the old cards of a book that fails."""
    accts = accounts(uid)
    allc, errors, books = [], [], []
    for a in accts:
        try:
            allc += await fetch_account(a, books)
        except (ValueError, httpx.HTTPError) as e:
            errors.append(f"{a.get('name', '')}: {e if isinstance(e, ValueError) else type(e).__name__}")
            books += [b for b in _raw(uid).get("books") or [] if b.get("acc") == a.get("id")]
    if errors and not allc:
        _save(uid, errors=errors)
        hintergrund.note(uid, "contacts", False)
        return public(uid)
    seen, uniq = set(), []
    for x in allc:
        k = (x["name"].lower(), tuple(p[1] for p in x["phones"]))
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    _save(uid, cards=uniq, errors=errors, books=books)
    hintergrund.note(uid, "contacts", not errors, len(uniq))
    return public(uid)


async def add(uid, item):
    accts = accounts(uid)
    if len(accts) >= MAX_ACCOUNTS:
        raise ValueError(f"höchstens {MAX_ACCOUNTS} Adressbücher")
    found = await fetch_account(item)   # only saved when it could be read
    _save(uid, accts + [item])
    await refresh(uid)
    return dict(public(uid), check=len(found))


async def due_once(now=None):
    """Once a day per profile that uses contacts."""
    now = now or time.time()
    for uid in profiles.user_ids():
        try:
            if usable(uid) and now - (_raw(uid).get("fetched") or 0) > REFRESH:
                await refresh(uid)
        except Exception as e:
            print("contacts:", type(e).__name__, flush=True)


# ---------------------------------------------------------------- lookups
def _norm(s):
    return re.sub(r"\s+", " ", re.sub(r"[^\w@.+ ]", " ", (s or "").lower())).strip()


def search(uid, query, limit=5):
    q = _norm(query)
    if len(q) < 2:
        return []
    words = q.split()
    out = []
    for x in cards(uid):
        hay = _norm(" ".join([x["name"], x.get("nick", ""), x.get("org", "")] + x.get("emails", [])))
        if all(w in hay for w in words):
            out.append((0, x))
        else:   # a misheard name: close enough to one of the name parts
            parts = hay.split()
            if all(difflib.get_close_matches(w, parts, n=1, cutoff=0.8) for w in words):
                out.append((1, x))
    out.sort(key=lambda t: (t[0], len(t[1]["name"])))
    return [x for _, x in out[:limit]]


def _bday_text(b, today):
    m = re.fullmatch(r"(\d{4}|-)-(\d\d)-(\d\d)", b or "")
    if not m:
        return ""
    s = f"{int(m.group(3))}. {MONTHS[int(m.group(2)) - 1]}"
    if m.group(1) != "-":
        s += f" {m.group(1)}"
    return s


def line(x, today=None):
    today = today or datetime.date.today()
    bits = [x["name"]] + ([f"Spitzname {x['nick']}"] if x.get("nick") else []) + ([x["org"]] if x.get("org") and x["org"] != x["name"] else [])
    s = ", ".join(bits)
    if x.get("phones"):
        s += "; " + ", ".join(f"{k} {n}" for k, n in x["phones"])
    if x.get("emails"):
        s += "; E-Mail " + ", ".join(x["emails"])
    if x.get("bday"):
        s += "; Geburtstag " + _bday_text(x["bday"], today)
    return s


def birthdays(uid, day, days=1):
    """[(date, name, age or None)] in [day, day+days)."""
    out = []
    for x in cards(uid):
        m = re.fullmatch(r"(\d{4}|-)-(\d\d)-(\d\d)", x.get("bday") or "")
        if not m:
            continue
        for k in range(days):
            d = day + datetime.timedelta(days=k)
            if (d.month, d.day) == (int(m.group(2)), int(m.group(3))) or \
                    ((int(m.group(2)), int(m.group(3))) == (2, 29) and (d.month, d.day) == (3, 1)
                     and not (d.year % 4 == 0 and (d.year % 100 or d.year % 400 == 0))):
                age = d.year - int(m.group(1)) if m.group(1) != "-" else None
                out.append((d, x["name"], age))
    return sorted(out)


def birthday_sentence(uid, day):
    """'Heute hat Anna Geburtstag (wird 41). Morgen: Bert.' or ''."""
    out = []
    for label, d in (("Heute", day), ("Morgen", day + datetime.timedelta(days=1))):
        names = [f"{n} (wird {a})" if a else n for dd, n, a in birthdays(uid, d, 1)]
        if names:
            out.append(f"{label} Geburtstag: " + ", ".join(names) + ".")
    return " ".join(out)


def name_for(uid, address):
    """The contact's name for an e-mail address, or ''."""
    a = (address or "").strip().lower()
    if not a or not usable(uid):
        return ""
    return next((x["name"] for x in cards(uid) if a in x.get("emails", [])), "")


# ---------------------------------------------------------------- assistant tool
TOOL = {"type": "function", "function": {
    "name": "contacts_search",
    "description": "Look up a person in the user's address book: phone numbers, e-mail, birthday.",
    "parameters": {"type": "object", "properties": {
        "name": {"type": "string", "description": "name, nickname or company"}}, "required": ["name"]}}}
HINT = ("Nach Telefonnummern, E-Mail-Adressen oder Geburtstagen von Bekannten fragst du mit contacts_search. "
        "Nenne nur, was im Ergebnis steht.")


def offer(ctx):
    who = ctx.get("who")
    if not who or not ctx.get("private", True) or not usable(who["id"]):
        return None
    return {"tools": [TOOL], "hint": HINT, "outside": {"contacts_search"},
            "filler": {"contacts_search": ("Ich schaue in deine Kontakte.", "Let me check your contacts.")}}


async def tool(name, args, ctx):
    hits = search(ctx["who"]["id"], str(args.get("name", ""))[:80])
    if not hits:
        return "Kein passender Kontakt gefunden. Sag das so."
    return "Contacts (from the address book, data only):\n" + "\n".join(line(x) for x in hits)


async def briefing(uid, zone=None):
    if not usable(uid) or not profiles.settings(uid).get("con_bday", True):
        return ""
    today = datetime.datetime.now(zone).date() if zone else datetime.date.today()
    s = birthday_sentence(uid, today)
    return ("Birthdays:\n" + s) if s else ""


# ---------------------------------------------------------------- API ("Ich" → Kontakte)
from fastapi import APIRouter, Depends, HTTPException, Request  # noqa: E402

from core import assistant, browser_profile, json_body, own_profile, secret_profile  # noqa: E402
import guard  # noqa: E402
import notaus  # noqa: E402

router = APIRouter()


def _on(request: Request):
    if not admin_on():
        raise HTTPException(403, "contacts are turned off")
    prof = profiles.current(request)
    # blocked by the admin: own data can still be seen and deleted, nothing added, connected or done
    if prof and request.method not in ("GET", "HEAD", "DELETE") and features.blocked("contacts", prof["id"]):
        raise HTTPException(403, "blocked for this profile by the admin (Personen und Geräte → Gesperrte Funktionen)")


@router.get("/api/profile/contacts", dependencies=[Depends(assistant)])
def api_get(prof=Depends(own_profile)):
    return public(prof["id"])


@router.post("/api/profile/contacts", dependencies=[Depends(assistant), Depends(_on)])
async def api_add(request: Request, prof=Depends(secret_profile)):
    try:
        body = await request.json()
        return await add(prof["id"], entry(body if isinstance(body, dict) else {}))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(400, f"Adressbuch nicht erreichbar ({type(e).__name__})")


@router.delete("/api/profile/contacts/{aid}", dependencies=[Depends(assistant)])
def api_remove(aid: str, prof=Depends(browser_profile)):
    return remove(prof["id"], aid)


def _clear(uid):
    for x in accounts(uid):
        remove(uid, x["id"])


# own data for Ich while the admin blocks contacts for the profile (features.OWN): the address books (their copy goes along)
features.OWN["contacts"] = (lambda uid: len(accounts(uid)), _clear)


@router.post("/api/profile/contacts/refresh", dependencies=[Depends(assistant), Depends(_on)])
async def api_refresh(prof=Depends(own_profile)):
    return await refresh(prof["id"])


@router.post("/api/profile/contacts/find", dependencies=[Depends(assistant), Depends(_on)])
async def api_find(request: Request, prof=Depends(own_profile)):
    body = await request.json()
    return {"lines": [line(x) for x in search(prof["id"], str((body or {}).get("name", ""))[:80])]}


# ---------------------------------------------------------------- the page Kontakte (Apple-Stil „6a“)
# Like Apple Kontakte: the address books as groups, A–Z, a card with its buttons and „Mit Anna“. Changing needs the
# admin switch „Kontakte ändern“ (chat.contacts_edit, off): a card goes back into its own address book with its ETag
# (If-Match; changed meanwhile → 409, nothing overwritten), a new one into the book chosen or the Spark's own one.
_page = {"day": "", "n": 0}


def page_today():
    return _page["n"] if _page["day"] == time.strftime("%Y-%m-%d") else 0


def _counted():
    day = time.strftime("%Y-%m-%d")
    if _page["day"] != day:
        _page.update(day=day, n=0)
    _page["n"] += 1


def _vid(x):
    """A card read without its own place (several cards in one object): an id for showing only."""
    return "v" + hashlib.sha1(json.dumps([x.get("name"), x.get("phones"), x.get("emails")]).encode()).hexdigest()[:12]


def books(uid):
    """[{id, name, account, write}] of the profile's address books and the Spark's own one."""
    names = {a["id"]: a.get("name", "") for a in accounts(uid)}
    d = _raw(uid)
    out = [{"id": b["id"], "name": b.get("name") or names.get(b.get("acc"), ""), "account": names.get(b.get("acc"), ""),
            "write": True} for b in d.get("books") or [] if b.get("acc") in names]
    if _spark(d) or features.allowed("kontakteaendern", uid):
        out.append({"id": SPARK, "name": "Auf dem Spark", "account": "Spark", "write": True})
    return out


_SHOW = ("name", "given", "family", "nick", "org", "title", "phones", "emails", "addrs", "urls", "note", "bday", "book")


def page(uid):
    """The page Kontakte: the books, every card (without its place on the server), whether it may change."""
    edit, ok = features.allowed("kontakteaendern", uid), {b["id"] for b in books(uid)}
    out = []
    for x in cards(uid):
        cid = x.get("id") or _vid(x)
        out.append(dict({k: x.get(k, [] if k in ("phones", "emails", "addrs", "urls") else "") for k in _SHOW},
                        id=cid, etag=x.get("etag", ""), edit=bool(edit and x.get("id") and x.get("book") in ok)))
    out.sort(key=lambda c: (c["family"] or c["name"]).lower())
    d = _raw(uid)
    return {"books": books(uid), "cards": out, "edit": edit, "fetched": d.get("fetched"), "errors": d.get("errors") or []}


def _find(uid, cid):
    x = next((c for c in cards(uid) if c.get("id") == cid), None)
    if x is None:
        raise LookupError("the contact is not there as shown (changed meanwhile)")
    return x


def _place(uid, bid):
    """(account, book href) of an address book of the profile."""
    b = next((b for b in _raw(uid).get("books") or [] if b.get("id") == bid), None)
    a = next((a for a in accounts(uid) if b and a["id"] == b.get("acc")), None)
    if a is None:
        raise LookupError("no such address book")
    return a, b["href"]


def _keep(uid, cid, card):
    """The Spark's copy after a change: card None removes it."""
    d = _raw(uid)
    if card is not None and card.get("book") == SPARK or cid.startswith("s"):
        sp = [c for c in _spark(d) if c.get("id") != cid] + ([card] if card is not None else [])
        _save(uid, spark=sp)
        return
    try:
        cache = json.loads(vault.open_(d.get("cache", "")) or "[]")
    except ValueError:
        cache = []
    cache = [c for c in cache if c.get("id") != cid] + ([card] if card is not None else [])
    with _lock:
        d = _raw(uid)
        d["cache"] = vault.seal(json.dumps(cache, ensure_ascii=False))
        profiles._write(_file(uid), d)
        _mem.pop(uid, None)


async def _get(c, href):
    r = await c.get(href)
    if r.status_code == 404:
        raise LookupError("the contact is not there as shown (changed meanwhile)")
    if r.status_code != 200 or "BEGIN:VCARD" not in r.text:
        raise ValueError(f"the address book answered {r.status_code}")
    return r.text, r.headers.get("etag", "")


def _card(text, cid, bid, href, etag):
    x = parse_vcard(text)
    if x is None:
        raise ValueError("not a vCard")
    return dict(x, id=cid, book=bid, href=href, etag=etag)


async def save(uid, cid, bid, f, seen=""):
    """A new card (cid None, into book bid) or a change of card cid; seen: the ETag the page showed. Returns the
    card as the page shows it. One journal line for every outcome."""
    who = profiles.log_name(profiles.by_id(uid))
    what = "added" if cid is None else "changed"
    try:
        notaus.stop("aktion", uid)
        if cid is None and bid == SPARK:
            sid = "s" + os.urandom(6).hex()
            _, text = kontaktkarte.new(f)
            card = dict(_card(text, sid, SPARK, "", ""), vcf=text)
        elif cid is None:
            a, book = _place(uid, bid)
            uid_text, text = kontaktkarte.new(f)
            href = urljoin(book.rstrip("/") + "/", re.sub(r"[^\w.-]", "", uid_text.split("@")[0]) + ".vcf")
            async with _client(a, seen=False) as c:
                r = await c.put(href, content=text.encode(), headers={"If-None-Match": "*", "Content-Type": "text/vcard; charset=utf-8"})
                if r.status_code not in (200, 201, 204):
                    raise ValueError(f"the address book answered {r.status_code}")
                text, etag = await _get(c, href)
            card = _card(text, _cid(a["id"], href), bid, href, etag)
        else:
            x = _find(uid, cid)
            if x.get("book") == SPARK:
                text = kontaktkarte.patch(x["vcf"], f)
                # the object name a contacts app gave it (kontaktserver.py) stays, so the app sees a change
                card = dict(_card(text, cid, SPARK, "", ""), vcf=text, **({"dav": x["dav"]} if x.get("dav") else {}))
            else:
                a, _book = _place(uid, x.get("book"))
                async with _client(a, seen=False) as c:
                    text, etag = await _get(c, x["href"])
                    if seen and etag and seen != etag:
                        raise LookupError("the contact was changed meanwhile in its address book")
                    new = kontaktkarte.patch(text, f)
                    r = await c.put(x["href"], content=new.encode(),
                                    headers=dict({"Content-Type": "text/vcard; charset=utf-8"}, **({"If-Match": etag} if etag else {})))
                    if r.status_code == 412:
                        raise LookupError("the contact was changed meanwhile in its address book")
                    if r.status_code not in (200, 201, 204):
                        raise ValueError(f"the address book answered {r.status_code}")
                    text, etag = await _get(c, x["href"])
                card = _card(text, cid, x["book"], x["href"], etag)
        _keep(uid, card["id"], card)
    except notaus.NotausAktiv:
        print(f"contacts: card refused, notaus | {who}", flush=True)
        raise
    except LookupError:
        print(f"contacts: card refused, changed meanwhile | {who}", flush=True)
        raise
    except Exception as e:
        print(f"contacts: card not {what} ({type(e).__name__}) | {who}", flush=True)
        raise
    _counted()
    print(f"contacts: card {what} | {who}", flush=True)
    return next(c for c in page(uid)["cards"] if c["id"] == card["id"])


async def delete(uid, cid, seen=""):
    """Deletes card cid from its address book (If-Match) or from the Spark's own one."""
    who = profiles.log_name(profiles.by_id(uid))
    try:
        notaus.stop("aktion", uid)
        x = _find(uid, cid)
        if x.get("book") != SPARK:
            a, _book = _place(uid, x.get("book"))
            async with _client(a, seen=False) as c:
                _text, etag = await _get(c, x["href"])
                if seen and etag and seen != etag:
                    raise LookupError("the contact was changed meanwhile in its address book")
                r = await c.delete(x["href"], headers={"If-Match": etag} if etag else {})
                if r.status_code == 412:
                    raise LookupError("the contact was changed meanwhile in its address book")
                if r.status_code not in (200, 204):
                    raise ValueError(f"the address book answered {r.status_code}")
        _keep(uid, cid, None)
    except notaus.NotausAktiv:
        print(f"contacts: card delete refused, notaus | {who}", flush=True)
        raise
    except LookupError:
        print(f"contacts: card delete refused, changed meanwhile | {who}", flush=True)
        raise
    except Exception as e:
        print(f"contacts: card not deleted ({type(e).__name__}) | {who}", flush=True)
        raise
    _counted()
    print(f"contacts: card deleted | {who}", flush=True)


def vcf(uid, cid):
    """One card as a .vcf file to pass on („Teilen“): the page's fields, nothing of the address book's own lines."""
    x = next((c for c in page(uid)["cards"] if c["id"] == cid), None)
    if x is None:
        raise LookupError("no such contact")
    body = dict(x, phones=[p for p in x["phones"] if p[0] in kontaktkarte.PHONE_KINDS],
                addrs=[a for a in x["addrs"] if a.get("kind") in kontaktkarte.ADDR_KINDS])
    if not (x["given"] or x["family"] or x["org"]):
        body["given"] = x["name"]
    return kontaktkarte.new(kontaktkarte.fields(body))[1]


async def with_(uid, cid, zone):
    """„Mit Anna“: the next appointment with the person (in 60 days, by mail address or name) and the newest mail
    from them in the Spark's mail supply; only what is switched on, nothing fetched for it from a mailbox."""
    x = next((c for c in page(uid)["cards"] if c["id"] == cid), None)
    if x is None:
        raise LookupError("no such contact")
    mails = [m.lower() for m in x["emails"]]
    name = x["name"].lower()
    out = {"event": None, "mail": None}
    if features.allowed("calendar", uid):
        import calendars
        now = datetime.datetime.now(zone)
        try:
            got = await calendars.events(uid, now, now + datetime.timedelta(days=60), zone, stale=True)
        except Exception:
            got = None
        for ev in (got or ([], []))[0]:
            people = {p.get("mail", "").lower() for p in ev.get("people") or []}
            if people & set(mails) or (len(name) >= 4 and name in ev["title"].lower()):
                out["event"] = {"title": ev["title"], "start": int(ev["start"].timestamp()), "allday": ev["allday"]}
                break
    if mails and features.allowed("mail", uid):
        import mail
        import mailvorrat
        best = None
        for a in mail.get(uid)["accounts"]:
            hits, _at = mailvorrat.heads(uid, a["id"], lambda h: any(m in str(h.get("from", "")).lower() for m in mails),
                                         365, False, 1)
            for _aid, _u, h in hits:
                if best is None or h["date"] > best["date"]:
                    best = h
        if best:
            out["mail"] = {"subject": str(best.get("subject", ""))[:200], "date": int(best["date"].timestamp())}
    return out


def for_live():
    """Live: address books, cards in the Spark's own book, changes on the page today (numbers only, never whose)."""
    n_books = n_spark = 0
    for uid in profiles.user_ids():
        d = _raw(uid)
        n_books += len(d.get("books") or [])
        n_spark += len(_spark(d))
    return {"books": n_books, "spark": n_spark, "today": page_today()}


def _edit(request: Request):
    prof = profiles.current(request)
    if not prof or not features.allowed("kontakteaendern", prof["id"]):
        raise HTTPException(403, "Kontakte ändern ist aus (Funktionen → Kontakte → Kontakte ändern)")


@router.get("/api/profile/contacts/page", dependencies=[Depends(assistant), Depends(_on)])
def api_page(request: Request, prof=Depends(own_profile)):
    guard.limit(request, "kontakte", prof["id"])
    if not features.allowed("contacts", prof["id"]):
        raise HTTPException(403, "contacts are turned off")
    return page(prof["id"])


@router.get("/api/profile/contacts/with/{cid}", dependencies=[Depends(assistant), Depends(_on)])
async def api_with(cid: str, request: Request, tz: str = "", prof=Depends(own_profile)):
    guard.limit(request, "kontakte", prof["id"])
    from chat import user_zone
    try:
        return await with_(prof["id"], cid[:20], user_zone(tz[:64]))
    except LookupError as e:
        raise HTTPException(404, str(e))


@router.get("/api/profile/contacts/vcf/{cid}", dependencies=[Depends(assistant), Depends(_on)])
def api_vcf(cid: str, request: Request, prof=Depends(own_profile)):
    from fastapi.responses import Response
    guard.limit(request, "kontakte", prof["id"])
    try:
        text = vcf(prof["id"], cid[:20])
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e)[:200])
    return Response(text, media_type="text/vcard; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="kontakt.vcf"'})


async def _answer(job):
    try:
        return await job
    except notaus.NotausAktiv:
        raise HTTPException(423, "Notaus: gerade wird nichts geändert")
    except LookupError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e)[:200])
    except httpx.HTTPError:
        raise HTTPException(502, "Das Adressbuch ist nicht erreichbar.")


@router.post("/api/profile/contacts/card", dependencies=[Depends(assistant), Depends(_on), Depends(_edit)])
async def api_card_add(request: Request, prof=Depends(browser_profile)):
    guard.limit(request, "kontakte", prof["id"])
    body = await json_body(request, 64 * 1024)
    try:
        f = kontaktkarte.fields(body)
    except ValueError as e:
        print(f"contacts: card form refused | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(400, str(e)[:200])
    return await _answer(save(prof["id"], None, str(body.get("book") or SPARK)[:20], f))


@router.put("/api/profile/contacts/card/{cid}", dependencies=[Depends(assistant), Depends(_on), Depends(_edit)])
async def api_card_change(cid: str, request: Request, prof=Depends(browser_profile)):
    guard.limit(request, "kontakte", prof["id"])
    body = await json_body(request, 64 * 1024)
    try:
        f = kontaktkarte.fields(body)
    except ValueError as e:
        print(f"contacts: card form refused | {profiles.log_name(prof)}", flush=True)
        raise HTTPException(400, str(e)[:200])
    return await _answer(save(prof["id"], cid[:20], None, f, str(body.get("etag") or "")[:200]))


@router.delete("/api/profile/contacts/card/{cid}", dependencies=[Depends(assistant), Depends(_on), Depends(_edit)])
async def api_card_delete(cid: str, request: Request, etag: str = "", prof=Depends(browser_profile)):
    guard.limit(request, "kontakte", prof["id"])
    await _answer(delete(prof["id"], cid[:20], etag[:200]))
    return {"ok": True}
