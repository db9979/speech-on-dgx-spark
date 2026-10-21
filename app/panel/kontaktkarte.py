"""Kontakte wie Apple Kontakte (Apple-Stil „6a“, Dominik 2026-10-21 „Weiter“): the fields of a contact the page Kontakte
and the iPhone app edit, checked, and written into a vCard. Pure functions without the network: contacts.py reads the
card fresh from its address book, writes it back with its ETag and keeps the Spark's copy.

Only the fields the page shows are replaced (name, company, job title, phones, mails, addresses, web addresses,
birthday, note); everything else of the card (photo, UID, groups, the address book's own lines) stays as it was.
Everything read from a card is data: names and numbers only as text."""
import datetime
import os
import re

PHONES_MAX = 8
MAILS_MAX = 6
ADDRS_MAX = 4
URLS_MAX = 4
NOTE_MAX = 2000
# the labels of the page (Apple: Mobil, Privat, Arbeit …) and their vCard TYPE; parse_vcard reads them the same way
PHONE_KINDS = {"Handy": "CELL", "Privat": "HOME", "Arbeit": "WORK", "Telefon": "VOICE"}
ADDR_KINDS = {"Privat": "HOME", "Arbeit": "WORK", "Adresse": ""}
# the lines this page owns in a card; a grouped one (item1.TEL with item1.X-ABLabel) goes with its whole group
OWNED = {"FN", "N", "ORG", "TITLE", "NICKNAME", "TEL", "EMAIL", "ADR", "URL", "NOTE", "BDAY"}
_MAIL = re.compile(r"[^@\s<>\"(),;:\\]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,24}")
_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def _text(v, n):
    return _CTRL.sub(" ", str(v or "")).strip()[:n]


def fields(body):
    """The page's fields, checked (ValueError for a wrong one, never guessed). A contact needs a name or a company."""
    given, family = _text(body.get("given"), 80), _text(body.get("family"), 80)
    org, title, nick = _text(body.get("org"), 120), _text(body.get("title"), 120), _text(body.get("nick"), 60)
    if not (given or family or org):
        raise ValueError("a contact needs a name or a company")
    phones = []
    for p in (body.get("phones") if isinstance(body.get("phones"), list) else [])[:PHONES_MAX + 1]:
        kind, num = (p[0], p[1]) if isinstance(p, (list, tuple)) and len(p) == 2 else ("Telefon", p)
        num = str(num or "").strip()
        if not num:
            continue
        if not re.fullmatch(r"\+?[\d /()\-.]{3,30}", num):
            raise ValueError("a phone number has only digits, spaces, + / ( ) - and .")
        phones.append([kind if kind in PHONE_KINDS else "Telefon", num])
    mails = []
    for m in (body.get("emails") if isinstance(body.get("emails"), list) else [])[:MAILS_MAX + 1]:
        m = str(m or "").strip()
        if not m:
            continue
        if not _MAIL.fullmatch(m):
            raise ValueError("a mail address looks like anna@example.org")
        if m.lower() not in mails:
            mails.append(m.lower())
    addrs = []
    for a in (body.get("addrs") if isinstance(body.get("addrs"), list) else [])[:ADDRS_MAX + 1]:
        if not isinstance(a, dict):
            raise ValueError("an address has street, zip, city and country")
        x = {k: _text(a.get(k), 120) for k in ("street", "zip", "city", "country")}
        if any(x.values()):
            addrs.append(dict(x, kind=a.get("kind") if a.get("kind") in ADDR_KINDS else "Adresse"))
    urls = []
    for u in (body.get("urls") if isinstance(body.get("urls"), list) else [])[:URLS_MAX + 1]:
        u = str(u or "").strip()
        if not u:
            continue
        if not re.fullmatch(r"https?://[^\s<>\"]{1,300}", u):
            raise ValueError("a web address starts with https:// or http://")
        urls.append(u)
    if len(phones) > PHONES_MAX or len(mails) > MAILS_MAX or len(addrs) > ADDRS_MAX or len(urls) > URLS_MAX:
        raise ValueError("too many fields")
    bday = str(body.get("bday") or "").strip()
    if bday:
        m = re.fullmatch(r"(\d{4}|-)-(\d\d)-(\d\d)", bday)
        try:
            datetime.date(2000 if m.group(1) == "-" else int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except (AttributeError, ValueError):
            raise ValueError("the birthday is a date like 1985-03-15 (or --03-15 without the year)")
    note = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(body.get("note") or "")).replace("\r", "").strip()[:NOTE_MAX]
    return {"given": given, "family": family, "org": org, "title": title, "nick": nick, "phones": phones,
            "emails": mails, "addrs": addrs, "urls": urls, "bday": bday, "note": note}


def _esc(v):
    return str(v).replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")


def _fold(line):
    """RFC 6350: lines longer than 75 octets go on with a space, never inside a character."""
    out, cur = [], ""
    for ch in line:
        if len((cur + ch).encode()) > (75 if not out else 74):
            out.append(cur)
            cur = ch
        else:
            cur += ch
    return "\r\n ".join(out + [cur])


def display(f):
    return " ".join(x for x in (f["given"], f["family"]) if x) or f["org"]


def lines(f):
    """The page's fields as vCard lines (without BEGIN, VERSION, UID, END)."""
    out = [f"FN:{_esc(display(f))}", f"N:{_esc(f['family'])};{_esc(f['given'])};;;"]
    if f["nick"]:
        out.append(f"NICKNAME:{_esc(f['nick'])}")
    if f["org"]:
        out.append(f"ORG:{_esc(f['org'])}")
    if f["title"]:
        out.append(f"TITLE:{_esc(f['title'])}")
    for kind, num in f["phones"]:
        out.append(f"TEL;TYPE={PHONE_KINDS[kind]}:{num}")
    for m in f["emails"]:
        out.append(f"EMAIL;TYPE=INTERNET:{m}")
    for a in f["addrs"]:
        t = ADDR_KINDS[a["kind"]]
        out.append(f"ADR{';TYPE=' + t if t else ''}:;;{_esc(a['street'])};{_esc(a['city'])};;{_esc(a['zip'])};{_esc(a['country'])}")
    for u in f["urls"]:
        out.append(f"URL:{u}")
    if f["bday"]:
        y, mo, d = re.fullmatch(r"(\d{4}|-)-(\d\d)-(\d\d)", f["bday"]).groups()
        out.append(f"BDAY:{'--' + mo + d if y == '-' else y + '-' + mo + '-' + d}")
    if f["note"]:
        out.append(f"NOTE:{_esc(f['note'])}")
    return out


def _unfold(text):
    return re.sub(r"\r?\n[ \t]", "", text.replace("\r\n", "\n")).split("\n")


def patch(text, f, now=None):
    """The card text with the page's fields in place of its own lines; every other line stays (REV is set anew)."""
    rows = [r for r in _unfold(text) if r.strip()]
    if not rows or rows[0].upper() != "BEGIN:VCARD" or rows[-1].upper() != "END:VCARD":
        raise ValueError("not one vCard")
    if sum(1 for r in rows if r.upper() == "BEGIN:VCARD") != 1:
        raise ValueError("not one vCard")

    def key(r):
        return r.split(":", 1)[0].split(";", 1)[0]
    # more of a kind than the page shows would be lost: such a card is changed only in its address book's program
    for k, most in (("TEL", PHONES_MAX), ("EMAIL", MAILS_MAX), ("ADR", ADDRS_MAX), ("URL", URLS_MAX)):
        if sum(1 for r in rows if key(r).split(".")[-1].upper() == k) > most:
            raise ValueError("this card has more fields than the page shows; change it in its address book's program")
    groups = {key(r).split(".")[0].upper() for r in rows if "." in key(r) and key(r).split(".")[-1].upper() in OWNED}
    keep = [r for r in rows[1:-1] if key(r).split(".")[-1].upper() not in OWNED | {"REV"}
            and not ("." in key(r) and key(r).split(".")[0].upper() in groups)]
    rev = (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    body = keep[:1] + lines(f) + keep[1:] + [f"REV:{rev}"] if keep and keep[0].upper().startswith("VERSION") \
        else ["VERSION:3.0"] + lines(f) + keep + [f"REV:{rev}"]
    return "\r\n".join(["BEGIN:VCARD"] + [_fold(r) for r in body] + ["END:VCARD"]) + "\r\n"


def new(f, uid_text=None):
    """A new card: (its UID, its text)."""
    uid_text = uid_text or f"{os.urandom(8).hex()}@speech-spark"
    text = patch(f"BEGIN:VCARD\r\nVERSION:3.0\r\nUID:{uid_text}\r\nEND:VCARD\r\n", f)
    return uid_text, text
