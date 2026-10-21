"""Kontakte wie Apple Kontakte, Stufe 3b (Apple-Stil „6a“, Dominik 2026-10-21 „Weiter“): the Spark as a CardDAV
server, so the iPhone's own Kontakte app (or Thunderbird, DAVx5 on Android) shows and changes the profile's address
book „Auf dem Spark“ directly.

Who may: the admin switch chat.contacts_server (features.py "kontaktserver", off by default, needs Kontakte and the
Kalender-Server), every profile the admin did not block, never guests. The door is the Kalender-Server's
(kalenderserver.login): HTTP Basic with the profile's id and its app password from Kalender → Einstellungen → „Für
Kalender-Apps“, wrong guesses lock like a PIN, guard.RATE "caldav", a web page of another site is refused, Mein
Notaus closes it. Changing, adding and deleting only with „Kontakte ändern“ (features "kontakteaendern"); without it
the address book is read-only (403 on PUT and DELETE).

- Only the profile's own address book „Auf dem Spark“ (contacts.SPARK), nothing of its iCloud or other address books
  (the iPhone has those itself) and nothing of another profile. The path names the profile; another one's is 404.
- What comes in is data: one vCard per object, at most MAX_TEXT characters and MAX_CARDS cards, an object name of
  letters, digits and „._@-“ only, a name or a company (contacts.parse_vcard); the text is kept sealed as it came,
  the page shows only what parse_vcard reads from it. If-Match / If-None-Match as the app sends them.
- Journal: fixed words and numbers; Live: requests, saved changes and refusals today.
"""
import hashlib
import os
import re
from urllib.parse import unquote
from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

import contacts
import features
import kalenderserver
import notaus
import profiles
from common import DayCounter

router = APIRouter()
PREFIX = "/carddav/"
BOOK = "spark"                     # the one address book under the profile's path
NAME = re.compile(r"[A-Za-z0-9._@-]{1,200}\.vcf")
MAX_TEXT = 256 * 1024              # characters of one card (a photo fits)
MAX_CARDS = 2000                   # cards in the address book „Auf dem Spark“
METHODS = ["OPTIONS", "PROPFIND", "REPORT", "GET", "HEAD", "PUT", "DELETE", "PROPPATCH", "MKCOL"]
DAV = "1, 2, addressbook"
_count = DayCounter(anfragen=0, gespeichert=0, abgelehnt=0)
_NS = ('xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav" xmlns:cs="http://calendarserver.org/ns/"')
_RIGHTS = ("<d:current-user-privilege-set><d:privilege><d:read/></d:privilege>{}</d:current-user-privilege-set>")


def admin_on():
    return features.admin_on("kontaktserver")


def _who(uid):
    return profiles.log_name(profiles.by_id(uid))


def _etag(text):
    return '"' + hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:20] + '"'


def _name(card):
    """The object name of a card: the one the app gave it, else the Spark's id."""
    return card.get("dav") or card["id"] + ".vcf"


def _cards(uid):
    return {_name(c): c for c in contacts._spark(contacts._raw(uid)) if c.get("vcf")}


def _ms(responses):
    body = f'<?xml version="1.0" encoding="utf-8"?><d:multistatus {_NS}>' + "".join(responses) + "</d:multistatus>"
    return Response(content=body.encode(), status_code=207, headers={"Content-Type": "application/xml; charset=utf-8"})


def _resp(href, props):
    return (f"<d:response><d:href>{escape(href)}</d:href><d:propstat><d:prop>{props}</d:prop>"
            "<d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>")


def _gone(href):
    return f"<d:response><d:href>{escape(href)}</d:href><d:status>HTTP/1.1 404 Not Found</d:status></d:response>"


def _book(uid, write):
    cards = _cards(uid)
    ctag = hashlib.sha1("".join(sorted(_etag(c["vcf"]) for c in cards.values())).encode()).hexdigest()[:16]
    return _resp(f"{PREFIX}{uid}/{BOOK}/", "<d:resourcetype><d:collection/><card:addressbook/></d:resourcetype>"
                                           "<d:displayname>Auf dem Spark</d:displayname>"
                                           f"<cs:getctag>{ctag}</cs:getctag>"
                                           "<card:max-resource-size>" + str(MAX_TEXT) + "</card:max-resource-size>"
                 + _RIGHTS.format("<d:privilege><d:write/></d:privilege>" if write else ""))


def _item(uid, n, card, data):
    return _resp(f"{PREFIX}{uid}/{BOOK}/{n}", f"<d:getetag>{escape(_etag(card['vcf']))}</d:getetag>"
                                               "<d:getcontenttype>text/vcard; charset=utf-8</d:getcontenttype>"
                 + (f"<card:address-data>{escape(card['vcf'])}</card:address-data>" if data else ""))


def _valid(text):
    """One vCard with a name or a company, not too long; None if not."""
    if len(text) > MAX_TEXT or text.upper().count("BEGIN:VCARD") != 1:
        return None
    return contacts.parse_vcard(text)


def _write(uid, method, n, have, headers, body):
    """PUT or DELETE of one card; (status, etag or "")."""
    match, none = headers.get("if-match"), headers.get("if-none-match")
    if (match and match.strip() != "*" and (have is None or match.strip() != _etag(have["vcf"]))) \
            or (match and have is None) or (none == "*" and have is not None):
        return 412, ""
    spark = contacts._spark(contacts._raw(uid))
    if method == "DELETE":
        if have is None:
            return 404, ""
        contacts._save(uid, spark=[c for c in spark if c.get("id") != have["id"]])
        return 204, ""
    text = (body or b"").decode("utf-8", "replace").replace("\r\n", "\n").replace("\n", "\r\n")
    x = _valid(text)
    if x is None:
        return 415, ""
    if have is None and len(spark) >= MAX_CARDS:
        return 507, ""
    cid = have["id"] if have else "s" + os.urandom(6).hex()
    card = dict(x, id=cid, book=contacts.SPARK, href="", etag="", vcf=text, dav=n)
    contacts._save(uid, spark=[c for c in spark if c.get("id") != cid] + [card])
    return (201 if have is None else 204), _etag(text)


@router.api_route("/.well-known/carddav", methods=["GET", "PROPFIND", "OPTIONS"])
def well_known():
    """RFC 6764: the contacts app finds the server from the bare address."""
    if not admin_on():
        raise HTTPException(404, "not found")
    return Response(status_code=301, headers={"Location": PREFIX})


@router.api_route("/carddav", methods=METHODS)
@router.api_route("/carddav/{rest:path}", methods=METHODS)
async def carddav(request: Request, rest: str = ""):
    if not admin_on():
        raise HTTPException(404, "not found")
    method = request.method.upper()
    if method == "OPTIONS" and not request.headers.get("authorization"):
        return Response(status_code=200, headers={"DAV": DAV, "Allow": ", ".join(METHODS)})
    uid, refused = kalenderserver.login(request)
    if refused:
        return refused
    if not features.allowed("kontaktserver", uid):
        _count.bump("abgelehnt")
        print(f"contacts: carddav refused, switched off | {_who(uid)}", flush=True)
        return Response(status_code=403)
    _count.bump("anfragen")
    write = features.allowed("kontakteaendern", uid)
    parts = [unquote(p) for p in rest.split("/") if p]
    body = await request.body() if method in ("PROPFIND", "REPORT", "PUT", "PROPPATCH") else b""
    home = f"{PREFIX}{uid}/"
    if method == "OPTIONS":
        return Response(status_code=200, headers={"DAV": DAV, "Allow": ", ".join(METHODS)})
    if not parts:   # the root: who is logged in
        if method != "PROPFIND":
            return Response(status_code=405)
        return _ms([_resp(PREFIX, "<d:resourcetype><d:collection/></d:resourcetype>"
                                  f"<d:current-user-principal><d:href>{home}</d:href></d:current-user-principal>"
                                  f"<card:addressbook-home-set><d:href>{home}</d:href></card:addressbook-home-set>")])
    if parts[0] != uid or len(parts) > 3:
        return Response(status_code=404)   # only the logged-in profile's own path
    if len(parts) == 1:   # the profile: principal and address book home in one
        if method != "PROPFIND":
            return Response(status_code=403 if method in ("PROPPATCH", "MKCOL") else 405)
        name = escape((profiles.by_id(uid) or {}).get("name") or "Spark")
        out = [_resp(home, "<d:resourcetype><d:collection/><d:principal/></d:resourcetype>"
                           f"<d:displayname>{name}</d:displayname>"
                           f"<d:current-user-principal><d:href>{home}</d:href></d:current-user-principal>"
                           f"<d:principal-URL><d:href>{home}</d:href></d:principal-URL>"
                           f"<card:addressbook-home-set><d:href>{home}</d:href></card:addressbook-home-set>")]
        if request.headers.get("depth", "0") == "1":
            out.append(_book(uid, write))
        return _ms(out)
    if parts[1] != BOOK:
        return Response(status_code=404)
    cards = _cards(uid)
    if len(parts) == 2:   # the address book
        if method == "PROPFIND":
            out = [_book(uid, write)]
            if request.headers.get("depth", "0") == "1":
                out += [_item(uid, n, c, False) for n, c in cards.items()]
            return _ms(out)
        if method == "REPORT":
            if b"sync-collection" in body:
                return Response(status_code=403)   # not offered: the app compares the etags instead
            if b"addressbook-multiget" in body:
                want = [h.decode("utf-8", "replace").rsplit("/", 1)[-1]
                        for h in re.findall(rb"<(?:\w+:)?href>\s*([^<\s]+)\s*<", body)[:MAX_CARDS]]
                return _ms([_item(uid, n, cards[n], True) if n in cards else _gone(f"{home}{BOOK}/{n}")
                            for n in dict.fromkeys(unquote(w) for w in want) if NAME.fullmatch(n)])
            return _ms([_item(uid, n, c, True) for n, c in cards.items()])   # addressbook-query: all of them
        return Response(status_code=403 if method in ("PROPPATCH", "MKCOL") else 405)
    n = parts[2]
    if not NAME.fullmatch(n):
        return Response(status_code=404)
    have = cards.get(n)
    if method in ("GET", "HEAD", "PROPFIND"):
        if have is None:
            return Response(status_code=404)
        if method == "PROPFIND":
            return _ms([_item(uid, n, have, False)])
        return Response(content=have["vcf"].encode() if method == "GET" else b"", status_code=200,
                        headers={"ETag": _etag(have["vcf"]), "Content-Type": "text/vcard; charset=utf-8"})
    if method not in ("PUT", "DELETE"):
        return Response(status_code=405)
    if not write:
        _count.bump("abgelehnt")
        print(f"contacts: carddav not saved, read only | {_who(uid)}", flush=True)
        return Response(status_code=403)
    try:
        notaus.stop("aktion", uid)
    except notaus.NotausAktiv:
        print(f"contacts: carddav not saved, notaus | {_who(uid)}", flush=True)
        return Response(status_code=423)
    status, etag = _write(uid, method, n, have, request.headers, body)
    if status < 300:
        _count.bump("gespeichert")
        print(f"contacts: carddav {'deleted' if method == 'DELETE' else 'saved'} | {_who(uid)}", flush=True)
    else:
        _count.bump("abgelehnt")
        print(f"contacts: carddav not saved ({status}) | {_who(uid)}", flush=True)
    return Response(status_code=status, headers={"ETag": etag} if etag else {})


def for_live():
    """Live (Kontakte): requests, saved changes and refusals today; numbers only."""
    c = _count.counts()
    return {"on": admin_on(), "requests": c.get("anfragen", 0), "saved": c.get("gespeichert", 0),
            "refused": c.get("abgelehnt", 0)}
