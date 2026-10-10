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
import json
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

import httpx

import netguard
import profiles
import vault
import features
from common import load_config

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


def _save(uid, accts=None, cards=None, errors=None):
    with _lock:
        d = _raw(uid)
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
    d = _raw(uid)
    hit = _mem.get(uid)
    if hit and hit[0] == d.get("fetched"):
        return hit[1]
    try:
        out = json.loads(vault.open_(d.get("cache", "")) or "[]")
    except ValueError:
        out = []
    _mem[uid] = (d.get("fetched"), out)
    return out


def usable(uid):
    return bool(features.allowed("contacts", uid) and accounts(uid))


def public(uid):
    d = _raw(uid)
    return {"accounts": [{"id": x["id"], "name": x.get("name", ""), "url": x["url"], "user": x.get("user", "")}
                         for x in accounts(uid)],
            "count": len(cards(uid)), "fetched": d.get("fetched"), "errors": d.get("errors") or [],
            "on": bool(profiles.settings(uid).get("con_on"))}


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
    _save(uid, rest, [] if not rest else None)
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
    """{"name", "nick", "org", "phones": [(kind, number)], "emails": [...], "bday": "YYYY-MM-DD" or "--MM-DD"}"""
    c = {"name": "", "nick": "", "org": "", "phones": [], "emails": [], "bday": ""}
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
        elif key == "NICKNAME":
            c["nick"] = _val(value)[:60]
        elif key == "ORG":
            c["org"] = _val(value.split(";")[0])[:80]
        elif key == "TEL" and len(c["phones"]) < 6:
            kind = "Handy" if "cell" in ptxt or "iphone" in ptxt or "mobile" in ptxt else \
                "Arbeit" if "work" in ptxt else "Privat" if "home" in ptxt else "Telefon"
            num = re.sub(r"[^\d+ /()\-]", "", value.replace("tel:", ""))[:30].strip()
            if num:
                c["phones"].append([kind, num])
        elif key == "EMAIL" and len(c["emails"]) < 4:
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
    return out


async def _cards(c, book):
    """vCard texts of one address book: addressbook-query, else list + multiget."""
    q = ('<?xml version="1.0"?><a:addressbook-query xmlns:d="DAV:" xmlns:a="urn:ietf:params:xml:ns:carddav">'
         '<d:prop><d:getetag/><a:address-data/></d:prop></a:addressbook-query>')
    r = await c.request("REPORT", book, content=q, headers={"Depth": "1", "Content-Type": "application/xml"})
    root = _xml(r.content) if r.status_code == 207 else None
    texts = [x.text for x in root.iter("{urn:ietf:params:xml:ns:carddav}address-data")] if root is not None else []
    texts = [x for x in texts if x and "BEGIN:VCARD" in x]
    if texts:
        return texts
    root = await _propfind(c, book, '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop><d:getetag/></d:prop></d:propfind>', 1)
    hrefs = [h.text.strip() for h in (root.iter("{DAV:}href") if root is not None else []) if h.text]
    hrefs = [h for h in hrefs if urljoin(book, h).rstrip("/") != book.rstrip("/")][:MAX_CONTACTS]
    for i in range(0, len(hrefs), 200):
        body = ('<?xml version="1.0"?><a:addressbook-multiget xmlns:d="DAV:" xmlns:a="urn:ietf:params:xml:ns:carddav">'
                '<d:prop><a:address-data/></d:prop>' + "".join(f"<d:href>{h}</d:href>" for h in hrefs[i:i + 200])
                + "</a:addressbook-multiget>")
        r = await c.request("REPORT", book, content=body, headers={"Depth": "1", "Content-Type": "application/xml"})
        root = _xml(r.content) if r.status_code == 207 else None
        texts += [x.text for x in (root.iter("{urn:ietf:params:xml:ns:carddav}address-data") if root is not None else [])
                  if x.text and "BEGIN:VCARD" in x.text]
    return texts


async def fetch_account(acct):
    auth = (acct["user"], acct.get("password", "")) if acct.get("user") else None
    async with netguard.client(netguard.USER, origin=acct["url"], timeout=httpx.Timeout(30, connect=8), auth=auth,
                               follow_redirects=True, headers={"User-Agent": "speech-on-dgx-spark"}) as c:
        books = await _books(c, acct["url"])
        if not books:
            raise ValueError("kein Adressbuch unter dieser Adresse gefunden")
        out = []
        for b in books[:10]:
            for t in await _cards(c, b):
                for part in re.findall(r"BEGIN:VCARD.*?END:VCARD", t, re.S):
                    x = parse_vcard(part)
                    if x:
                        out.append(x)
        return out[:MAX_CONTACTS]


async def refresh(uid):
    """Fetches every address book of the profile; keeps the old cards of a book that fails."""
    accts = accounts(uid)
    allc, errors = [], []
    for a in accts:
        try:
            allc += await fetch_account(a)
        except (ValueError, httpx.HTTPError) as e:
            errors.append(f"{a.get('name', '')}: {e if isinstance(e, ValueError) else type(e).__name__}")
    if errors and not allc:
        _save(uid, errors=errors)
        return public(uid)
    seen, uniq = set(), []
    for x in allc:
        k = (x["name"].lower(), tuple(p[1] for p in x["phones"]))
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    _save(uid, cards=uniq, errors=errors)
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

from core import assistant, browser_profile, own_profile, secret_profile  # noqa: E402

router = APIRouter()


def _on():
    if not admin_on():
        raise HTTPException(403, "contacts are turned off")


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


@router.post("/api/profile/contacts/refresh", dependencies=[Depends(assistant), Depends(_on)])
async def api_refresh(prof=Depends(own_profile)):
    return await refresh(prof["id"])


@router.post("/api/profile/contacts/find", dependencies=[Depends(assistant), Depends(_on)])
async def api_find(request: Request, prof=Depends(own_profile)):
    body = await request.json()
    return {"lines": [line(x) for x in search(prof["id"], str((body or {}).get("name", ""))[:80])]}
