"""Mail formatted like it was sent (Apple-Stil Stufe 1, Dominik 2026-10-20 „2a“): the HTML part of a mail as the page
E-Mail shows it, made safe here on the Spark before any browser sees it.

The HTML comes from other people, so it is data and goes through a fixed allow-list, never through the browser first:
- Tags: text formatting, lists, tables, quotes, links and pictures stay (ALLOWED); scripts, styles, frames, forms,
  SVG, media and the head go with their content (DROP); every other tag is left out, its text stays.
- Attributes: only the few of ATTRS; every on…= handler and every unknown attribute is left out. style keeps plain
  declarations only: no url(), no expression, no escapes, no position or z-index (a mail never lays itself over the
  page).
- Links: never a working href. The address goes into data-href (http, https and mailto only), the page shows it before
  it opens anything (post.js); a mail cannot navigate the frame or the page. The iPhone app gets a real href (live):
  its web view runs no script, stops every navigation and asks with the address before Safari opens it.
- Pictures: a picture attached to the mail (cid:) gets data-cid with the number of its part; a picture from outside
  gets data-remote and no src, so nothing is loaded and no sender learns that the mail was opened. Only „Bilder laden“
  (one click for one mail) lets the page fetch them, through the Spark (netguard), never straight from the browser.
- Text and attribute values are escaped anew; comments, doctype and processing instructions are left out.

The page shows the result in a frame of its own with a strict Content-Security-Policy (no script at all, sandbox).
"""
import asyncio
import base64
import html
import html.parser
import imaplib
import re
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

import features
import guard
import mail
import netguard
import profiles
from common import DayCounter
from core import assistant, mail_on, own_profile

IN_MAX = 1024 * 1024        # characters of a mail's HTML looked at
OUT_MAX = 400 * 1024        # characters of clean HTML handed out
STYLE_MAX = 1000            # characters of one style attribute kept
REMOTE_MAX = 60             # pictures from outside one mail may name
DATA_IMG_MAX = 200 * 1024   # characters of one data:image picture kept

ALLOWED = frozenset((
    "a", "abbr", "address", "b", "bdi", "bdo", "big", "blockquote", "br", "caption", "center", "cite", "code", "col",
    "colgroup", "dd", "del", "dfn", "div", "dl", "dt", "em", "figcaption", "figure", "font", "h1", "h2", "h3", "h4", "h5",
    "h6", "hr", "i", "img", "ins", "kbd", "li", "mark", "ol", "p", "pre", "q", "s", "samp", "small", "span", "strike",
    "strong", "sub", "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "tt", "u", "ul", "var", "wbr"))
# a new one of these ends the open one before it (what a browser does with <td>1<td>2)
AUTOCLOSE = {"td": ("td", "th"), "th": ("td", "th"), "tr": ("td", "th", "tr"), "li": ("li",), "dt": ("dt", "dd"),
             "dd": ("dt", "dd")}
VOID = frozenset(("br", "col", "hr", "img", "wbr"))
# every element HTML never closes: a dropped one of them (input, meta, …) must not swallow the rest of the mail
NO_END = VOID | frozenset(("area", "base", "basefont", "embed", "frame", "input", "keygen", "link", "meta", "param", "source", "track"))
# left out with everything inside them
DROP = frozenset((
    "applet", "audio", "base", "basefont", "button", "canvas", "datalist", "dialog", "embed", "form", "frame", "frameset",
    "head", "iframe", "input", "link", "map", "math", "meta", "noembed", "noframes", "noscript", "object", "option",
    "param", "picture", "portal", "script", "select", "source", "style", "svg", "template", "textarea", "title", "track",
    "video", "xml"))
ATTRS = frozenset(("align", "valign", "width", "height", "colspan", "rowspan", "dir", "bgcolor", "color", "face",
                   "size", "border", "cellpadding", "cellspacing", "alt", "title", "start", "type", "span"))
NUMERIC = frozenset(("width", "height", "size", "border", "cellpadding", "cellspacing", "colspan", "rowspan", "span", "start"))
SIZE_RX = re.compile(r"^[\w #%.,\-]{1,40}$")
STYLE_BAD = re.compile(r"url\s*\(|expression|javascript:|vbscript:|@|\\|/\*|behavior|-moz-binding|<|>", re.I)
STYLE_NOPROP = frozenset(("position", "z-index", "behavior", "-moz-binding", "content", "cursor", "pointer-events",
                          "top", "left", "right", "bottom", "inset"))
LINK_RX = re.compile(r"^(https?://[^\s\x00-\x1f]{1,2000}|mailto:[^\s\x00-\x1f]{1,500})$", re.I)
DATA_IMG_RX = re.compile(r"^data:image/(png|jpeg|gif|webp);base64,[A-Za-z0-9+/=\s]+$", re.I)


def _style(value):
    """Plain declarations only: name: value pairs without url(), escapes, comments or layering."""
    keep = []
    for decl in str(value)[:STYLE_MAX * 2].split(";"):
        name, sep, val = decl.partition(":")
        name = name.strip().lower()
        if not sep or not re.fullmatch(r"-?[a-z][a-z\-]{0,40}", name) or name in STYLE_NOPROP:
            continue
        val = val.strip()
        if not val or STYLE_BAD.search(val) or len(val) > 200:
            continue
        keep.append(f"{name}:{val}")
    return ";".join(keep)[:STYLE_MAX]


class _Clean(html.parser.HTMLParser):
    def __init__(self, cids, cid_src=None, remote_src=None, live=False):
        super().__init__(convert_charrefs=True)
        self.live = live          # the iPhone app: a real href, its web view stops every tap and asks first
        self.cids = cids          # {content id (lower case, without <>): part number}
        self.cid_src, self.remote_src, self.remote_urls = cid_src, remote_src, []
        self.out, self.open, self.drop = [], [], 0
        self.remote, self.links, self.size = 0, 0, 0

    def _put(self, s):
        if self.size < OUT_MAX:
            self.out.append(s)
            self.size += len(s)

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if self.drop or tag in DROP:
            if tag in DROP and tag not in NO_END:
                self.drop += 1
            return
        if tag not in ALLOWED:
            return
        while self.open and self.open[-1] in AUTOCLOSE.get(tag, ()):   # <td>1<td>2, <li>a<li>b as browsers read them
            self._put(f"</{self.open.pop()}>")
        kept = []
        for k, v in attrs:
            k, v = (k or "").lower(), "" if v is None else str(v)
            if k in ATTRS:
                if k in NUMERIC and not SIZE_RX.match(v):
                    continue
                kept.append((k, v[:300]))
            elif k == "style":
                s = _style(v)
                if s:
                    kept.append(("style", s))
            elif k == "href" and tag == "a" and LINK_RX.match(v.strip()):
                kept.append(("href" if self.live else "data-href", v.strip()))
                self.links += 1
            elif k == "src" and tag == "img":
                src = v.strip()
                if src.lower().startswith("cid:") and src[4:].strip("<>").lower() in self.cids:
                    n = self.cids[src[4:].strip("<>").lower()]
                    url = self.cid_src(n) if self.cid_src else None
                    kept.append(("src", url) if url else ("data-cid", str(n)))
                elif re.match(r"^https?://", src, re.I) and self.remote < REMOTE_MAX and len(src) <= 2000:
                    kept.append(("src", self.remote_src(src)) if self.remote_src else ("data-remote", src))
                    self.remote += 1
                    self.remote_urls.append(src)
                elif DATA_IMG_RX.match(src) and len(src) <= DATA_IMG_MAX:
                    kept.append(("src", re.sub(r"\s", "", src)))
        if tag == "img" and not any(k in ("data-cid", "data-remote", "src") for k, _ in kept):
            alt = next((v for k, v in kept if k == "alt"), "")
            if alt:
                self._put(html.escape(f"[{alt[:80]}]", quote=False))
            return
        self._put("<" + tag + "".join(f' {k}="{html.escape(v, quote=True)}"' for k, v in kept) + ">")
        if tag not in VOID:
            self.open.append(tag)

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if self.drop or tag in DROP:     # <svg/>, <iframe/>: nothing inside, nothing to count
            return
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.open and self.open[-1] == tag:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in DROP:
            if self.drop and tag not in NO_END:
                self.drop -= 1
            return
        if self.drop or tag not in ALLOWED or tag in VOID or tag not in self.open:
            return
        while self.open:                 # close what was left open inside it
            t = self.open.pop()
            self._put(f"</{t}>")
            if t == tag:
                break

    def handle_data(self, data):
        if not self.drop:
            self._put(html.escape(data, quote=False))

    def finish(self):
        while self.open:
            self._put(f"</{self.open.pop()}>")
        return "".join(self.out)


def clean(source, cids=None, cid_src=None, remote_src=None, live=False):
    """(safe HTML, pictures from outside, links) of a mail's HTML; cids = {content id: attachment number}. cid_src(n)
    and remote_src(address) give the src the Spark itself serves (else the picture keeps data-cid or data-remote)."""
    p = _Clean({str(k).strip("<>").lower(): int(v) for k, v in (cids or {}).items()}, cid_src, remote_src, live)
    try:
        p.feed(str(source or "")[:IN_MAX])
        p.close()
    except Exception:
        pass   # a broken mail shows what was read up to there
    return p.finish(), p.remote, p.links


def html_part(msg):
    """The mail's own HTML (the first text/html part that is not an attachment), None without one."""
    for part in msg.walk():
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        if part.get_content_type() == "text/html":
            try:
                return str(part.get_content())
            except Exception:
                return None
    return None


def inline_ids(msg, parts):
    """{content id: number} of the pictures among `parts` (mail.files order) that the HTML may show (cid:)."""
    out = {}
    for n, (part, _, _) in enumerate(parts):
        cid = str(part.get("Content-ID", "") or "").strip().strip("<>").lower()
        if cid and part.get_content_type() in IMAGE_TYPES:
            out[cid] = n
    return out


IMAGE_TYPES = frozenset(("image/png", "image/jpeg", "image/gif", "image/webp"))   # never SVG: it can carry script


# ------------------------------------------------------------------ the page E-Mail and the iPhone app
router = APIRouter()

# the frame of one mail: nothing runs (sandbox without scripts), nothing loads but the Spark's own pictures; the page
# (same origin) measures its height and catches a tap on a link, the frame itself can do neither
FRAME_CSP = ("default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; "
             "frame-ancestors 'self'; sandbox allow-same-origin")
FRAME_STYLE = ("html{color-scheme:light}body{margin:0;padding:2px 2px 8px;font:15px/1.55 -apple-system,system-ui,'Segoe UI',Roboto,sans-serif;"
               "color:#141824;background:#fff;overflow-wrap:anywhere}img{max-width:100%;height:auto}table{max-width:100%}"
               "a[data-href]{color:#4f46e5;text-decoration:underline;cursor:pointer}blockquote{margin:6px 0 6px 4px;padding-left:12px;"
               "border-left:3px solid #d6dbe6;color:#5f6b85}pre{white-space:pre-wrap}img[data-remote]{display:none}")
# the iPhone app (WKWebView without script, every load from outside blocked, every tap on a link asks first)
APP_CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
PICTURE_MAX = 3 * 1024 * 1024       # one picture from outside, fetched through the Spark
APP_INLINE_MAX = 6 * 1024 * 1024    # pictures put into the iPhone app's copy of one mail (data: addresses)
_counts = DayCounter(html=0, bilder=0)   # Live: mails shown formatted and pictures from outside loaded today (numbers)


def counts():
    return _counts.counts()


def _sniff(data):
    """The picture type from its first bytes, never from what the sender says (SVG never: it can carry script)."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _ref(ref, folder):
    return {"id": ref, **({"folder": folder} if folder and folder.upper() != "INBOX" else {})}


def document(uid, ref, folder="INBOX", pictures=False, inline=False):
    """The mail as a page of its own for the frame: (HTML, has HTML, pictures from outside). inline (the iPhone app):
    attached pictures as data: addresses instead of addresses on the Spark. Raises like mail.message; None when gone."""
    msg = mail.message(uid, ref, folder)
    if msg is None:
        return None
    src = html_part(msg)
    if src is None:
        text, _ = mail.plain(msg)
        body, n = f'<div style="white-space:pre-wrap">{html.escape(text or "", quote=False)}</div>', 0
    else:
        parts = mail.files(msg)
        cids = inline_ids(msg, parts)
        if inline:
            datas, used = {}, 0
            for n_, (part, _, size) in enumerate(parts):
                data = (part.get_payload(decode=True) or b"") if n_ in cids.values() else b""
                typ = _sniff(data)
                if typ and used + len(data) <= APP_INLINE_MAX:
                    datas[n_] = f"data:{typ};base64," + base64.b64encode(data).decode()
                    used += len(data)
            cid_src = lambda n_: datas.get(n_)  # noqa: E731
        else:
            cid_src = lambda n_: "/api/profile/mail/bild?" + urlencode({**_ref(ref, folder), "n": n_})  # noqa: E731
        remote_src = (lambda u: "/api/profile/mail/bild?" + urlencode({**_ref(ref, folder), "u": u})) if pictures and not inline else None
        body, n, _ = clean(src, cids, cid_src=cid_src, remote_src=remote_src, live=inline)
        _counts.bump("html")
    # the app shows the page from a string, without the header: the same policy goes into the page itself
    policy = f'<meta http-equiv="Content-Security-Policy" content="{APP_CSP}">' if inline else ""
    page = ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'{policy}<meta name="referrer" content="no-referrer"><style>{FRAME_STYLE}</style></head><body>{body}</body></html>')
    return page, src is not None, n


def _remote(src):
    """The addresses of the pictures from outside in a mail's HTML, in order (at most REMOTE_MAX)."""
    p = _Clean({})
    try:
        p.feed(src[:IN_MAX])
        p.close()
    except Exception:
        pass
    return p.remote_urls


def facts(uid, ref, folder="INBOX"):
    """What the page needs before it shows an own mail: {html: has an HTML part (then it is shown in the frame),
    remote: how many pictures from outside it names (the line „Bilder laden“)}. Same cached copy as mail.show."""
    msg = mail.message(uid, ref, folder)
    src = html_part(msg) if msg is not None else None
    return {"html": src is not None, "remote": len(_remote(src)) if src else 0}


def remote_list(uid, ref, folder="INBOX"):
    """The addresses of the pictures from outside this mail names (the only ones the Spark fetches for it)."""
    msg = mail.message(uid, ref, folder)
    src = html_part(msg) if msg is not None else None
    return _remote(src) if src else []


async def picture(url):
    """One picture from outside through the Spark (public addresses only, netguard): (type, bytes) or None."""
    try:
        async with netguard.client(netguard.PUBLIC, max_bytes=PICTURE_MAX, timeout=httpx.Timeout(10, connect=5),
                                   follow_redirects=True, headers={"User-Agent": "Mozilla/5.0", "Accept": "image/*"}) as c:
            r = await c.get(url)
    except (httpx.HTTPError, ValueError, OSError):
        return None
    data = r.content if r.status_code == 200 else b""
    typ = _sniff(data)
    return (typ, data) if typ and len(data) <= PICTURE_MAX else None


def _who(prof):
    return profiles.log_name(prof)


def _folder_ok(folder, prof):
    if folder and folder.upper() != "INBOX" and not features.allowed("mailmanage", prof["id"]):
        raise HTTPException(403, "Ordner gehören zu „Mails ordnen“.")
    return folder[:200] or "INBOX"


@router.get("/api/profile/mail/view", dependencies=[Depends(assistant), Depends(mail_on)])
async def mail_view(request: Request, id: str = "", folder: str = "", bilder: bool = False, app: bool = False,
                    prof=Depends(own_profile)):
    """One own mail formatted for the frame of the page (or the iPhone app: app=true, pictures inline). Its own strict
    policy: no script, nothing from outside; pictures from outside only with bilder=true, then through the Spark."""
    guard.limit(request, "post", prof["id"])
    folder = _folder_ok(folder, prof)
    try:
        got = await asyncio.wait_for(asyncio.to_thread(document, prof["id"], id[:40], folder, bilder, app), 45)
    except ValueError:
        raise HTTPException(400, "Unbekannte Mail.")
    except asyncio.TimeoutError:
        print(f"mail: view too slow | {_who(prof)}", flush=True)
        raise HTTPException(504, "Das Postfach hat zu lange gebraucht. Bitte gleich noch einmal.")
    except (OSError, imaplib.IMAP4.error):
        print(f"mail: view not readable | {_who(prof)}", flush=True)
        raise HTTPException(502, "Das Postfach war nicht erreichbar.")
    if got is None:
        raise HTTPException(404, "Diese Mail gibt es nicht mehr.")
    page, formatted, n = got
    print(f"mail: view {'html' if formatted else 'text'} | {n} pictures outside{' loaded' if bilder and n else ''} | {_who(prof)}", flush=True)
    return Response(page, media_type="text/html; charset=utf-8", headers={
        "Content-Security-Policy": FRAME_CSP, "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store", "X-Remote-Pictures": str(n)})


@router.get("/api/profile/mail/bild", dependencies=[Depends(assistant), Depends(mail_on)])
async def mail_picture(request: Request, id: str = "", folder: str = "", n: int = -1, u: str = "", prof=Depends(own_profile)):
    """A picture of an own mail for its frame: n = an attached picture (cid:), u = a picture from outside, fetched by
    the Spark only when this very mail names it. Only PNG, JPEG, GIF and WebP by their first bytes, never SVG."""
    guard.limit(request, "postbild", prof["id"])
    folder = _folder_ok(folder, prof)
    who = _who(prof)
    try:
        if u:
            urls = await asyncio.wait_for(asyncio.to_thread(remote_list, prof["id"], id[:40], folder), 45)
            if u not in urls:
                print(f"mail: picture refused, not in the mail | {who}", flush=True)
                raise HTTPException(404, "Dieses Bild steht nicht in der Mail.")
            got = await picture(u)
            if got is None:
                print(f"mail: picture not loaded | {who}", flush=True)
                raise HTTPException(404, "Das Bild kam nicht.")
            _counts.bump("bilder")
            print(f"mail: picture loaded | outside | {max(1, len(got[1]) // 1024)} KB | {who}", flush=True)
        else:
            msg = await asyncio.wait_for(asyncio.to_thread(mail.whole, prof["id"], id[:40], folder), 90)
            parts = mail.files(msg) if msg is not None else []
            data = (parts[n][0].get_payload(decode=True) or b"") if 0 <= n < len(parts) else b""
            typ = _sniff(data) if len(data) <= mail.FILE_MAX else None
            if not typ:
                print(f"mail: picture refused, no picture | {who}", flush=True)
                raise HTTPException(404, "Dieses Bild gibt es nicht.")
            got = (typ, data)
            print(f"mail: picture shown | attached | {max(1, len(data) // 1024)} KB | {who}", flush=True)
    except ValueError:
        print(f"mail: picture refused | {who}", flush=True)
        raise HTTPException(400, "Unbekannte Mail.")
    except asyncio.TimeoutError:
        print(f"mail: picture too slow | {who}", flush=True)
        raise HTTPException(504, "Das Postfach hat zu lange gebraucht.")
    except (OSError, imaplib.IMAP4.error):
        print(f"mail: picture not readable | {who}", flush=True)
        raise HTTPException(502, "Das Postfach war nicht erreichbar.")
    return Response(got[1], media_type=got[0], headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=600",
                                                        "Content-Security-Policy": "default-src 'none'; sandbox"})
