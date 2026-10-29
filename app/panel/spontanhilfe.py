"""Spontanhilfe (plan spontanhilfe, Dominik 2026-10-28 „ok“ to empfehlungen 10, 11, 14; Stufe S1: Ansehen und
Einladung; Stufe S3: Shell einmalig): an admin helps a person (family, friends) once at their computer, like TeamViewer
QuickSupport. Nothing is installed at the person's: the browser shares the screen, or (S3, a server without a screen)
one pasted line runs the anchor program once in her terminal; when either side ends, nothing is left.

    person (no profile, no guest)              panel (this module)                    admin's browser
    /hilfe  number + first name  ──POST /api/hilfe/start──►  one help, waiting
            WS /api/hilfe/ws  ◄────── relay of fixed message kinds ──────►  WS /api/spontanhilfe/admin?t=<ticket>
            getDisplayMedia ═══════════ WebRTC (DTLS-SRTP), TURN on tars when „Anrufe von unterwegs“ is on ════════► <video>

Rules (fixed, Sicherheits-Checkliste):
- Admin switch chat.spontanhilfe (Funktionen → Fernzugang zu Servern → Spontanhilfe, off, under the Fernzugang switch).
  Only admins in their own browser with a second sign-in step help. „Neue Hilfe“ asks for a fresh code or passkey
  (stufen „Schutz ändern“) and makes a number (NUMMER_S, 6 digits, once, dead after FEHL wrong tries) and a link key
  (LINK_S, 128 bits, behind „#“ so it never reaches a proxy log; only both hashes are kept). One help at a time.
- The person is no profile and no guest (Richtlinie, exception with its reason): she gets only this page, never a
  model, a tool or personal data. She types the number (or opens the link) and her first name, then the admin
  accepts with a fresh code („Annehmen“), then she clicks „Bildschirm teilen“ herself: both are needed.
- Every wrong number gets the same answer whatever the reason („Nummer nicht gültig“), compared in constant time,
  rate limited per address. The WebSockets check Origin themselves (the http middleware never sees them); the
  person's socket takes its key only in its first message (never in an address), the admin's a one-time ticket
  (TICKET_S, bound to the login). Only the message kinds in KINDS pass, each checked for form and size (MAX_MSG,
  CHAT_MAX); nothing of it is kept or logged. The picture never passes the panel: WebRTC between the two browsers.
- S3 Shell: „Neue Hilfe“ also shows one line for a terminal (fernzugang.command, art „hilfe“: the anchor program
  from /fernzugang/anker, the panel's certificate checked or pinned, no sudo, never a number in it). The program asks
  the number and the first name on the terminal and opens WS /api/hilfe/shell (a program: any Origin header is
  refused, so no web page can use it; the number in the first message, checked like /api/hilfe/start, the same
  rate limit). After „Annehmen“ the person is asked once more on her terminal („j“): only then the program starts her
  own shell in a PTY with her rights (never as root) and the bytes pass, binary, both ways (MAX_MSG each); before
  that nothing does. Strg+C, „Beenden“, the clock or the Notaus end it, and the program leaves nothing behind.
- A help lasts START_MIN minutes, „Verlängern“ (fresh code) adds PLUS_MIN, never past chat.spontanhilfe_max_min
  (default 180, 15 to 720); the admin's page warns HINWEIS_S before the end. Notaus ends it at once and kills
  number and link.
- Nothing is recorded, nothing goes to a model. Logs: „spontanhilfe: <word> | <reason> | <number>“, fixed words and
  numbers only, never the number, the key, the name, an address or the chat. Live: kind, count, minutes; names only
  with logs.live_names, never an address. The admin page shows „Gerade verbunden“ (admin, first name, Zuhause or
  Internet with a shortened address, since, what) and the „Verlauf“ (STATE/spontanhilfe-verlauf.json, the days of
  chat.fernzugang_verlauf_tage, no name and no content). The admins get a push when a person waits.

    admin (core.auth, the browser only):
    GET    /api/admin/spontanhilfe                     state, settings, history
    POST   /api/admin/spontanhilfe/neu {origin}        number and link (on the unlocked Fernzugang page)
    POST   /api/admin/spontanhilfe/einladung {an, en, nochmal}  the link by mail from the admin profile's own mailbox,
                                       once per help and address (409 „Einladung schon gesendet“)
    POST   /api/admin/spontanhilfe/annehmen            ticket for the admin's socket (on the unlocked page)
    POST   /api/admin/spontanhilfe/verlaengern         PLUS_MIN more (unlocked, and admin_code_fresh every time)
    DELETE /api/admin/spontanhilfe                     discard the number or end the help
    DELETE /api/admin/spontanhilfe/verlauf             empties the history (admin_code)
    (every door but GET and DELETE only while the Fernzugang page is unlocked, fernzugang._frei: rule „Bereich
    entsperren“; locked, GET tells only that it is on)
    WS     /api/spontanhilfe/admin?t=<ticket>          signalling, chat and „Zeigen“ for the admin
    person (no login):
    GET    /hilfe                                      the page (own strict CSP, display-capture only here)
    POST   /api/hilfe/start {nummer | link, name}      -> {tok, admin}
    WS     /api/hilfe/ws                               first message {"typ": "hallo", "tok"}; signalling, chat
    WS     /api/hilfe/shell                            (the anchor program, S3) first message {"typ": "hallo", "nummer",
                                                       "name", "os"}; „erlaubt“, then the terminal's bytes
"""
import asyncio
import contextlib
import email.message
import email.policy
import email.utils
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

import core
import features
import guard
import notaus
import profiles
from common import STATE, read_json, write_json
from core import admin_code, admin_code_fresh, auth, json_body

router = APIRouter()

VERLAUF = os.path.join(STATE, "spontanhilfe-verlauf.json")   # when, who helped, how long: no name, no content
PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "spontanhilfe.html")
NUMMER_S = 600          # the number works this long, once
LINK_S = 1800           # the link of an invitation (a mail can be slow), once
NOCHMAL_S = 60          # one invitation per help and address; „Nochmal senden“ (confirmed) only after this
FEHL = 5                # wrong numbers before the number is dead
TICKET_S = 30           # the admin's socket ticket
HALLO_S = 10            # the person's socket must say who it is this fast
START_MIN = 60          # a help starts with this many minutes
PLUS_MIN = 60           # „Verlängern“ adds this many
MAX_MIN = (15, 720)     # chat.spontanhilfe_max_min (default 180)
HINWEIS_S = 600         # the admin's page warns this long before the end
MAX_MSG = 16 * 1024     # one message on a socket
MAX_BODY = 4096
CHAT_MAX = 500
VERLAUF_MAX = 2000
NAME = re.compile(r"[^\W\d_][\w .'\-]{0,29}")
NUMMER = re.compile(r"\d{6}")
LINK = re.compile(r"[A-Za-z0-9_\-]{20,30}")
SDP = re.compile(r"v=0\r?\n[\x20-\x7e\r\n]*")
# what each side may send; the panel passes only these, checked for form and size
KINDS = {"person": {"sdp", "ice", "chat", "teilt", "ende"}, "admin": {"sdp", "ice", "chat", "zeig", "ende"},
         "shell_person": {"erlaubt", "ende"}, "shell_admin": {"groesse", "ende"}}   # S3: the terminal's bytes besides
ARTEN = {"ansehen": ("Ansehen", "View"), "shell": ("Shell", "Shell")}
OS = re.compile(r"[A-Za-z0-9 ._()\-]{1,40}")
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
PERMISSIONS = "display-capture=(self), microphone=(), camera=(), geolocation=(), payment=(), usb=(), serial=()"
MELDUNG_PUSH = ("Spontanhilfe wartet", "Eine Person hat die Nummer eingegeben und wartet. Annehmen unter Fernzugang → Spontanhilfe.")
VORLAGEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vorlagen")   # einladung.{de,en}.{txt,html}
BETREFF = {"de": "{name} möchte dir am Computer helfen", "en": "{name} would like to help you with your computer"}
FELD = re.compile(r"\{(name|name_s|link|nummer|gueltig|domain|min)\}")
WORDS = ("nummer_neu", "nummer_falsch", "nummer_tot", "verworfen", "einladung", "wartet", "ticket", "sitzung_auf",
         "sitzung_zu", "verlaengert", "abgewiesen", "verlauf", "meldung", "erlaubt")

HILFE = {}          # "h" -> the one Hilfe (or nothing)
TICKETS = {}        # sha256(ticket) -> {"login", "until"}
STATS = {"heute": "", "hilfen": 0, "falsch": 0}
_vlock = threading.Lock()
_TASKS = set()      # running pushes (kept so they are not collected early)


def log(word, why="", n=1):
    assert word in WORDS
    print(f"spontanhilfe: {word} | {why or '-'} | {n}", flush=True)


def _h(s):
    return hashlib.sha256(s.encode()).hexdigest()


# ---------------------------------------------------------------- switch and settings
def admin_on(c=None):
    """Funktionen → Fernzugang zu Servern → Spontanhilfe (admin, off); a Spark-wide door, no profile part."""
    return features.admin_on("spontanhilfe", c)


def max_min(c=None):
    c = features.chat_cfg() if c is None else c
    v = c.get("spontanhilfe_max_min")
    return v if isinstance(v, int) and not isinstance(v, bool) and MAX_MIN[0] <= v <= MAX_MIN[1] else 180


def check(c):
    v = c.get("spontanhilfe_max_min", 180)
    if not isinstance(v, int) or isinstance(v, bool) or not MAX_MIN[0] <= v <= MAX_MIN[1]:
        return f"chat.spontanhilfe_max_min: {MAX_MIN[0]} bis {MAX_MIN[1]}"
    return None


def _notaus(count=False):
    """The Notaus at any stage holds the Spontanhilfe off, like the Fernzugang (Spark-wide)."""
    if count:
        return notaus.refuse("aussen")
    return notaus.level() >= notaus.STAGE["aussen"]


# ---------------------------------------------------------------- the one help
class Hilfe:
    def __init__(self, uid, admin_name, login, nummer, link, now):
        self.id = secrets.token_hex(6)
        self.uid, self.admin_name, self.login = uid, admin_name, login
        self.nummer_h, self.link_h = _h(nummer), _h(link)
        self.nummer_bis, self.link_bis = now + NUMMER_S, now + LINK_S
        self.nummer = nummer          # kept in memory only, for the admin's own page and the invitation
        self.fehl = 0
        self.stand = "neu"            # neu -> wartet -> offen
        self.name = ""                # the first name as the person typed it (admin page only)
        self.tok_h = ""
        self.herkunft, self.ip_kurz = "zuhause", ""
        self.art = "ansehen"          # „shell“ when the person came through the anchor program (S3)
        self.os = ""                  # S3: the system the program named (admin page only)
        self.erlaubt = False          # S3: the person said „j“ on her terminal; only then bytes pass
        self.teilt = False
        self.erstellt = now
        self.seit = self.bis = 0.0
        self.hinweis = False
        self.person = self.admin = None   # the two sockets
        self.ende = None              # asyncio.Event, made by the first socket in the panel's loop
        self.grund = ""
        self.eingeladen = {}          # address (lower case) -> {"t": when, "laeuft": sending right now}

    def offen_fuer_nummer(self, now):
        return self.stand == "neu" and (now < self.nummer_bis or now < self.link_bis)


def current():
    return HILFE.get("h")


def _drop(h):
    if HILFE.get("h") is h:
        HILFE.pop("h", None)


def _admin_name(uid):
    p = profiles.by_id(uid) if uid else None
    return str(p.get("name") or "Admin")[:40] if p else "Admin"


def _live_names():
    try:
        import live
        return live.cfg().get("live_names") is True
    except Exception:
        return False


def for_live(now=None):
    """Live, Zustand, the apps: kind, count, minutes; names only with logs.live_names, never an address."""
    if not admin_on():
        return {"on": False}
    now = time.time() if now is None else now
    h = current()
    out = {"on": True, "nummer": 0, "wartet": 0, "sitzung": 0, "heute": STATS["hilfen"] if STATS["heute"] == time.strftime("%Y-%m-%d") else 0}
    if h is not None:
        if h.stand == "neu" and h.offen_fuer_nummer(now):
            out["nummer"] = 1
        elif h.stand == "wartet":
            out["wartet"] = 1
        elif h.stand == "offen":
            named = _live_names()
            out["sitzung"] = 1
            out["offen"] = {"art": ARTEN.get(h.art, ARTEN["ansehen"])[0], "admin": h.admin_name if named else "Admin",
                            "person": h.name if named else "Person",
                            "herkunft": "Internet" if h.herkunft == "internet" else "Zuhause",
                            "min": int((now - h.seit) // 60), "teilt": h.teilt}
    return out


def live_sub(d):
    if d.get("sitzung"):
        o = d["offen"]
        return f"1 Sitzung · {o['art']} {o['person']}, {o['admin']}, {o['herkunft']}, {o['min']} min"
    if d.get("wartet"):
        return "1 Person wartet"
    if d.get("nummer"):
        return "1 Nummer offen"
    return "bereit"


def _live(text):
    try:
        import live
        live.mark("Spontanhilfe", text)
    except Exception:
        pass


# ---------------------------------------------------------------- history (no name, no content)
def verlauf_s(c=None):
    import fernzugang
    return fernzugang.verlauf_s(c)


def verlauf_read(now=None):
    now = time.time() if now is None else now
    keep = verlauf_s()
    rows = read_json(VERLAUF, {}).get("eintraege") or []
    return [x for x in rows if isinstance(x, dict) and now - x.get("t", 0) <= keep]


def verlauf_add(h, now=None):
    now = time.time() if now is None else now
    with _vlock:
        rows = verlauf_read(now)
        rows.insert(0, {"t": int(h.seit or now), "admin": h.admin_name, "art": h.art,
                        "min": int((now - h.seit) // 60) if h.seit else 0, "herkunft": h.herkunft,
                        "ende": re.sub(r"[^a-z_]", "", h.grund)[:20]})
        write_json(VERLAUF, {"eintraege": rows[:VERLAUF_MAX]}, mode=0o600)
    log("verlauf", "neu", 1)


def verlauf_note(what, n, now=None):
    """A line without a session: a number that ran out or died (Verlauf „Nummer verfallen“, „Nummer gesperrt“)."""
    now = time.time() if now is None else now
    with _vlock:
        rows = verlauf_read(now)
        rows.insert(0, {"t": int(now), "art": what, "n": int(n)})
        write_json(VERLAUF, {"eintraege": rows[:VERLAUF_MAX]}, mode=0o600)
    log("verlauf", what, 1)


# ---------------------------------------------------------------- ends
async def end(h, why):
    if h is None or h.grund:
        return
    h.grund = why or "ende"
    _drop(h)
    if h.ende is not None:
        h.ende.set()
    for ws in (h.person, h.admin):
        if ws is None:
            continue
        with contextlib.suppress(Exception):
            await ws.send_text(json.dumps({"typ": "stand", "stand": "zu", "grund": h.grund}))
        with contextlib.suppress(Exception):
            await ws.close(1000)
    if h.stand == "offen":
        mins = int((time.time() - h.seit) // 60)
        log("sitzung_zu", h.grund, mins)
        await asyncio.to_thread(verlauf_add, h)
        _live(f"Spontanhilfe beendet ({h.grund})")
    else:
        log("verworfen", h.grund, 1)


async def close_all(why="notaus"):
    await end(current(), why)
    TICKETS.clear()


async def notaus_close():
    await close_all("notaus")


def _expire(now=None):
    """A number nobody used in time is gone (and noted in the history)."""
    now = time.time() if now is None else now
    h = current()
    if h is not None and h.stand == "neu" and not h.offen_fuer_nummer(now):
        _drop(h)
        log("verworfen", "abgelaufen", 1)
        verlauf_note("nummer_verfallen", h.fehl, now)


# ---------------------------------------------------------------- admin side
def _browser_admin(request):
    import fernzugang
    if not fernzugang.is_admin_browser(request):
        raise HTTPException(403, "only an admin in the browser")


def _on(request):
    if not admin_on():
        raise HTTPException(404, "Spontanhilfe ist aus (Funktionen → Fernzugang zu Servern → Spontanhilfe)")
    _browser_admin(request)
    if _notaus(count=True):
        log("abgewiesen", "notaus", 0)
        raise HTTPException(503, "Notaus: Spontanhilfe gesperrt")


def _frei(request):
    """The page Fernzugang unlocked for this login (rule „Bereich entsperren“): Spontanhilfe is one of its tabs."""
    import fernzugang
    fernzugang._frei(request)


def _second_step(request, word):
    import mfa
    prof = core.acting_profile(request)
    if not mfa.enabled(prof["id"] if prof else mfa.ADMIN):
        log(word, "kein zweiter schritt", 0)
        raise HTTPException(403, "Spontanhilfe nur mit zweitem Anmeldeschritt (Ich → Sicherheit).")


def _mine(request, h):
    import fernzugang
    if h is None or not hmac.compare_digest(h.login, fernzugang._login(request)):
        raise HTTPException(404, "keine Hilfe dieser Anmeldung")


def _view(h, now):
    if h is None:
        return None
    out = {"id": h.id, "stand": h.stand, "admin": h.admin_name, "art": h.art, "teilt": h.teilt, "os": h.os,
           "erlaubt": h.erlaubt}
    if h.stand == "neu":
        out.update(nummer=h.nummer, nummer_rest=max(0, int(h.nummer_bis - now)), link_rest=max(0, int(h.link_bis - now)),
                   fehl=h.fehl, fehl_max=FEHL)
    else:
        out.update(name=h.name, herkunft=h.herkunft, ip=h.ip_kurz)
    if h.stand == "offen":
        out.update(seit=int(h.seit), bis=int(h.bis), rest=max(0, int(h.bis - now)),
                   kann_verlaengern=h.bis - h.seit + 1 < max_min() * 60)
    return out


@router.get("/api/admin/spontanhilfe", dependencies=[Depends(auth)])
def admin_get(request: Request):
    _browser_admin(request)
    guard.limit(request, "spontanhilfe", admin=True)
    _expire()
    now = time.time()
    c = features.chat_cfg()
    import fernzugang
    if admin_on(c) and fernzugang.entsperrt_bis(request, now) is None:
        return {"on": True, "gesperrt": True, "notaus": _notaus()}   # locked page: nothing of a help or its history
    import anrufe
    return {"on": admin_on(c), "max_min": max_min(c), "start_min": START_MIN, "plus_min": PLUS_MIN, "hinweis_s": HINWEIS_S,
            "nummer_s": NUMMER_S, "link_s": LINK_S, "turn": anrufe.turn_on(), "hilfe": _view(current(), now),
            "notaus": _notaus(), "mail": _mail_ready(request),
            "verlauf": [{k: x.get(k) for k in ("t", "admin", "art", "min", "herkunft", "ende", "n")} for x in verlauf_read(now)[:200]],
            "verlauf_tage": verlauf_s(c) // 86400}


@router.post("/api/admin/spontanhilfe/neu", dependencies=[Depends(auth)])
async def admin_new(request: Request):
    """„Neue Hilfe“: a number and a link for the next person, on the unlocked page (its code or passkey came first)."""
    _on(request)
    _frei(request)
    _second_step(request, "nummer_neu")
    guard.limit(request, "spontanhilfe_neu", admin=True)
    body = await json_body(request, MAX_BODY)
    h = current()
    if h is not None and h.stand != "neu":
        log("nummer_neu", "belegt", 0)
        raise HTTPException(409, "Es läuft schon eine Hilfe. Erst beenden.")
    import fernzugang
    import terminal
    from common import load_config
    try:
        base = terminal.setup_base(body.get("origin"), load_config("panel"))
    except HTTPException:
        base = None
    now = time.time()
    nummer = f"{secrets.randbelow(10**6):06d}"
    link = secrets.token_urlsafe(16)
    prof = core.acting_profile(request)
    uid = prof["id"] if prof else None
    HILFE["h"] = Hilfe(uid, _admin_name(uid), fernzugang._login(request), nummer, link, now)
    log("nummer_neu", "admin" if not uid else "profil", 1)
    _live("Spontanhilfe: neue Nummer")
    url = f"{base[0]}/hilfe#{link}" if base else ""
    import mfa
    shell = fernzugang.command(body.get("origin"), art="hilfe") if base else None   # S3: one line for a terminal
    return {"nummer": nummer, "link": url, "qr": mfa._qr_svg(url) if url else "", "nummer_s": NUMMER_S, "link_s": LINK_S,
            "befehl": (shell or {}).get("befehl", ""), "befehl_mac": (shell or {}).get("befehl_mac", ""),
            "hilfe": _view(HILFE["h"], now)}


@router.delete("/api/admin/spontanhilfe", dependencies=[Depends(auth)])
async def admin_discard(request: Request):
    """„Verwerfen“ (a number) or „Beenden“ (a help): number and link stop at once."""
    _browser_admin(request)
    h = current()
    if h is None:
        return {"ok": True}
    await end(h, "admin")
    return {"ok": True}


@router.post("/api/admin/spontanhilfe/annehmen", dependencies=[Depends(auth)])
async def admin_accept(request: Request):
    """„Annehmen“: on the unlocked page a ticket that opens the admin's socket once, within TICKET_S seconds."""
    _on(request)
    _frei(request)
    _second_step(request, "ticket")
    guard.limit(request, "spontanhilfe_neu", admin=True)
    h = current()
    _mine(request, h)
    if h.stand != "wartet" or h.person is None:
        log("ticket", "keiner wartet", 0)
        raise HTTPException(409, "Niemand wartet.")
    import fernzugang
    t = secrets.token_urlsafe(32)
    now = time.time()
    for k in [k for k, v in TICKETS.items() if v["until"] < now]:
        TICKETS.pop(k, None)
    TICKETS[_h(t)] = {"login": fernzugang._login(request), "until": now + TICKET_S, "hid": h.id}
    log("ticket", "annehmen", 1)
    return {"ticket": t, "gilt_s": TICKET_S}


@router.post("/api/admin/spontanhilfe/verlaengern", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_extend(request: Request):
    """„Verlängern“: PLUS_MIN more, never past chat.spontanhilfe_max_min from the start (unlocked and a fresh code)."""
    _on(request)
    _frei(request)
    h = current()
    _mine(request, h)
    if h.stand != "offen":
        raise HTTPException(409, "Keine offene Hilfe.")
    room = h.seit + max_min() * 60 - h.bis
    if room < 60:
        log("verlaengert", "am ende", 0)
        raise HTTPException(409, f"Länger als {max_min()} Minuten geht nicht (Einstellung Spontanhilfe).")
    h.bis += min(PLUS_MIN * 60, room)
    h.hinweis = False
    log("verlaengert", "admin", int((h.bis - h.seit) // 60))
    await _both(h, {"typ": "zeit", "bis": int(h.bis), "rest": int(h.bis - time.time())})
    return {"bis": int(h.bis)}


@router.delete("/api/admin/spontanhilfe/verlauf", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_clear_history(request: Request):
    _browser_admin(request)
    _frei(request)
    with _vlock:
        n = len(verlauf_read())
        write_json(VERLAUF, {"eintraege": []}, mode=0o600)
    log("verlauf", "geloescht", n)
    return {"ok": True}


# ---------------------------------------------------------------- invitation by mail (senden.send_now, unchanged)
def _mail_acct(request):
    prof = core.acting_profile(request)
    if not prof:
        return None, None
    try:
        import mail
        accts = mail.get(prof["id"])["accounts"]
    except Exception:
        return prof, None
    if not accts or not features.allowed("mailsend", prof["id"]):
        return prof, None
    return prof, accts[0]


def _mail_ready(request):
    try:
        return _mail_acct(request)[1] is not None
    except Exception:
        return False


def _vorlage(name):
    with open(os.path.join(VORLAGEN, name), encoding="utf-8") as f:
        return f.read()


def invitation_text(admin, link, nummer, lang, bis):
    """The one place that fills the invitation: (subject, text, html, name), or None when a field would be empty.
    The templates are fixed files of the panel (vorlagen/, never edited by anyone); one pass of FELD, so a value
    is never read as a placeholder, and every value is HTML-escaped in the html part."""
    lang = "en" if lang == "en" else "de"
    admin = re.sub(r"[\x00-\x1f\x7f]", " ", str(admin or "")).strip()[:40]
    m = re.fullmatch(r"https://([A-Za-z0-9.\-]+)(?::\d{1,5})?/hilfe#[A-Za-z0-9_\-]{20,30}", link or "")
    if not admin or not m or not NUMMER.fullmatch(nummer or "") or not bis:
        return None
    if lang == "en":
        name_s = admin + "’s"
    else:
        name_s = admin + ("’" if admin[-1:].lower() in "sßxz" else "s")
    uhr = time.strftime("%H:%M", time.localtime(bis))
    werte = {"name": admin, "name_s": name_s, "link": link, "nummer": f"{nummer[:3]} {nummer[3:]}",
             "gueltig": uhr if lang == "en" else uhr + " Uhr", "domain": m.group(1), "min": str(LINK_S // 60)}
    text = FELD.sub(lambda x: werte[x.group(1)], _vorlage(f"einladung.{lang}.txt"))
    page = FELD.sub(lambda x: html.escape(werte[x.group(1)], quote=True), _vorlage(f"einladung.{lang}.html"))
    return BETREFF[lang].replace("{name}", admin), text, page, admin


def invitation(acct, prof, to, link, nummer, lang, bis):
    """The fixed invitation (de/en): text and the same as HTML (design „Karte“), from the admin's own mailbox."""
    filled = invitation_text(prof.get("name") or "Admin", link, nummer, lang, bis)
    if filled is None:
        return None
    subj, text, page, name = filled
    msg = email.message.EmailMessage(policy=email.policy.SMTP)
    msg["From"] = email.utils.formataddr((name, acct["user"]))
    msg["To"] = to
    msg["Subject"] = subj
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=acct["user"].rsplit("@", 1)[1])
    msg.set_content(text)
    msg.add_alternative(page, subtype="html")
    return msg


@router.post("/api/admin/spontanhilfe/einladung", dependencies=[Depends(auth)])
async def admin_invite(request: Request):
    """„Per E-Mail“: the link from the own mailbox of the admin profile (Funktionen → Mails senden on)."""
    _on(request)
    _frei(request)
    guard.limit(request, "spontanhilfe_neu", admin=True)
    body = await json_body(request, MAX_BODY)
    h = current()
    _mine(request, h)
    if h.stand != "neu" or time.time() >= h.link_bis:
        log("einladung", "kein link", 0)
        raise HTTPException(409, "Erst eine neue Hilfe anlegen.")
    import senden
    to = str(body.get("an") or "").strip()
    link = str(body.get("link") or "")
    if not senden.ADDR.fullmatch(to) or len(to) > 254:
        log("einladung", "adresse", 0)
        raise HTTPException(400, "an: eine E-Mail-Adresse")
    m = re.fullmatch(r"(https://[A-Za-z0-9.\-]+(?::\d{1,5})?)/hilfe#([A-Za-z0-9_\-]{20,30})", link)
    if not m or not hmac.compare_digest(_h(m.group(2)), h.link_h):
        log("einladung", "link", 0)
        raise HTTPException(400, "link: der Link dieser Hilfe")
    prof, acct = _mail_acct(request)
    if acct is None:
        log("einladung", "kein konto", 0)
        raise HTTPException(409, "Einladen per E-Mail braucht ein Admin-Profil mit E-Mail-Konto und „Mails senden“.")
    msg = invitation(acct, prof, to, link, h.nummer, "en" if body.get("en") else "de", h.link_bis)
    if msg is None:
        log("einladung", "leer", 1)
        raise HTTPException(409, "Die Einladung wäre unvollständig; nichts gesendet.")
    # one mail per help and address: marked before the first await, so a second click finds it (no lock needed,
    # the check and the mark run in one step of the panel's loop); „Nochmal senden“ only confirmed and after 60 s
    key, now = to.lower(), time.time()
    vorher = h.eingeladen.get(key)
    if vorher and (vorher["laeuft"] or body.get("nochmal") is not True or now - vorher["t"] < NOCHMAL_S):
        log("einladung", "doppelt", 0)
        raise HTTPException(409, "Einladung schon gesendet")
    h.eingeladen[key] = {"t": now, "laeuft": True}
    try:
        await asyncio.to_thread(senden.send_now, prof["id"], acct, msg)
    except Exception as e:
        if vorher:
            h.eingeladen[key] = vorher
        else:
            h.eingeladen.pop(key, None)
        log("einladung", "fehler", 0)
        raise HTTPException(502, f"Die Mail ging nicht hinaus ({type(e).__name__}).")
    h.eingeladen[key] = {"t": time.time(), "laeuft": False}
    log("einladung", "nochmal" if vorher else "mail", 1)
    return {"ok": True, "nochmal_ab": int(NOCHMAL_S)}


# ---------------------------------------------------------------- the person's side
def page(request: Request):
    """/hilfe: the page with its own strict CSP; screen sharing is allowed only here (Permissions-Policy)."""
    if not admin_on():
        raise HTTPException(404, "Not Found")
    with open(PAGE, encoding="utf-8") as f:
        html = f.read()
    return HTMLResponse(html, headers={"Content-Security-Policy": CSP, "Permissions-Policy": PERMISSIONS,
                                       "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
                                       "Cache-Control": "no-store"})


def _refused():
    return HTTPException(403, "Nummer nicht gültig")


def _pruefen(nummer, link, now=None):
    """The one waiting help when the number (or the link's key) is right, else None: compared in constant time, every
    wrong try counted, the number dead after FEHL (one rule for the page and the anchor program)."""
    _expire(now)
    now = time.time() if now is None else now
    h = current()
    ok = False
    if h is not None and h.stand == "neu":
        if link and LINK.fullmatch(link) and now < h.link_bis:
            ok = hmac.compare_digest(_h(link), h.link_h)
        elif nummer and NUMMER.fullmatch(nummer) and now < h.nummer_bis:
            ok = hmac.compare_digest(_h(nummer), h.nummer_h)
    if ok:
        return h
    STATS["falsch"] += 1
    if h is not None and h.stand == "neu":
        h.fehl += 1
        if h.fehl >= FEHL:
            _drop(h)
            log("nummer_tot", "fehlversuche", h.fehl)
            verlauf_note("nummer_gesperrt", h.fehl, now)
            _live("Spontanhilfe: Nummer gesperrt")
    log("nummer_falsch", "link" if link else "nummer", 1)
    return None


@router.post("/api/hilfe/start")
async def person_start(request: Request):
    """The number (or the link's key) and a first name: the same answer for every wrong try, whatever the reason."""
    if not admin_on():
        raise HTTPException(404, "Not Found")
    guard.limit(request, "spontanhilfe_start")
    if _notaus(count=True):
        log("abgewiesen", "notaus", 0)
        raise HTTPException(503, "Gerade nicht möglich.")
    body = await json_body(request, MAX_BODY)
    name = re.sub(r"\s+", " ", str(body.get("name") or "")).strip()
    if not NAME.fullmatch(name):
        raise HTTPException(400, "Bitte den Vornamen eingeben (Buchstaben, bis 30).")
    nummer, link = str(body.get("nummer") or "").replace(" ", ""), str(body.get("link") or "")
    h = _pruefen(nummer, link)
    if h is None:
        raise _refused()
    tok = secrets.token_urlsafe(32)
    h.tok_h, h.name, h.stand = _h(tok), name, "wartet"
    h.nummer = ""                       # used: not even the admin page shows it any more
    _wo(h, request)
    log("wartet", "link" if link else "nummer", 1)
    _live("Spontanhilfe: eine Person wartet")
    t = asyncio.create_task(_melden(h))
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)
    return {"tok": tok, "admin": h.admin_name}


def _wo(h, conn):
    import live
    try:
        h.herkunft = "internet" if live.shown_outside(conn) else "zuhause"
        h.ip_kurz = live.short_ip(live.sender(conn))
    except Exception:
        h.herkunft, h.ip_kurz = "zuhause", "?"


def _admins():
    import fernzugang
    return fernzugang._admins()


async def _melden(h):
    """A push to the admins when a person waits: fixed words, never her name or an address."""
    try:
        import push
        n = 0
        for uid in _admins():
            n += await push.send(uid, MELDUNG_PUSH[0], MELDUNG_PUSH[1], tag="admin", private=True, why="spontanhilfe")
        log("meldung", "push", n)
    except Exception as e:
        log("meldung", "fehler " + type(e).__name__.lower()[:20], 0)


def _same_origin(ws):
    import fernzugang
    return fernzugang.same_origin(ws)


def clean(side, m):
    """One message of one side, checked: its kind from KINDS[side] and the form of its fields; None when not."""
    if not isinstance(m, dict) or m.get("typ") not in KINDS[side]:
        return None
    t = m["typ"]
    if t == "sdp":
        want = "offer" if side == "person" else "answer"
        sdp = m.get("sdp")
        if m.get("art") != want or not isinstance(sdp, str) or len(sdp) > MAX_MSG - 512 or not SDP.fullmatch(sdp):
            return None
        return {"typ": "sdp", "art": want, "sdp": sdp}
    if t == "ice":
        c = m.get("c")
        if c is None:
            return {"typ": "ice", "c": None}
        if not isinstance(c, dict) or not isinstance(c.get("candidate"), str) or len(c["candidate"]) > 1024 \
                or not re.fullmatch(r"[\x20-\x7e]*", c["candidate"]):
            return None
        mid = c.get("sdpMid")
        idx = c.get("sdpMLineIndex")
        if mid is not None and (not isinstance(mid, str) or not re.fullmatch(r"[A-Za-z0-9_\-]{0,16}", mid)):
            return None
        if idx is not None and (not isinstance(idx, int) or isinstance(idx, bool) or not 0 <= idx < 16):
            return None
        return {"typ": "ice", "c": {"candidate": c["candidate"], "sdpMid": mid, "sdpMLineIndex": idx}}
    if t == "chat":
        s = m.get("text")
        if not isinstance(s, str):
            return None
        s = "".join(ch for ch in s if ch.isprintable() or ch == "\n").strip()[:CHAT_MAX]
        return {"typ": "chat", "text": s} if s else None
    if t == "zeig":
        x, y = m.get("x"), m.get("y")
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1 for v in (x, y)):
            return None
        return {"typ": "zeig", "x": round(float(x), 4), "y": round(float(y), 4)}
    if t in ("teilt", "erlaubt"):
        return {"typ": t, "an": m.get("an") is True}
    if t == "groesse":
        c, r = m.get("cols"), m.get("rows")
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (c, r)) or not (2 <= c <= 500 and 1 <= r <= 300):
            return None
        return {"typ": "groesse", "cols": c, "rows": r}
    return {"typ": "ende"}


async def _both(h, d):
    for ws in (h.person, h.admin):
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.send_text(json.dumps(d))


async def _send(ws, d):
    if ws is not None:
        with contextlib.suppress(Exception):
            await ws.send_text(json.dumps(d))


def _ice(h):
    import anrufe
    try:
        return anrufe.ice("spontanhilfe|" + h.id)
    except Exception:
        return []


async def _relay(h, side, ws):
    """Reads one side's socket until it closes; passes checked messages to the other side. S3 (art „shell“): the
    terminal's bytes too, binary, but only once the person allowed it on her terminal."""
    shell = h.art == "shell"
    kinds = ("shell_" if shell else "") + side
    while True:
        try:
            got = await ws.receive()
        except (WebSocketDisconnect, RuntimeError, KeyError):
            break
        if got.get("type") == "websocket.disconnect":
            break
        data, raw = got.get("bytes"), got.get("text")
        if len(data or raw or "") > MAX_MSG:
            log("abgewiesen", "zu gross", 0)
            break
        other = h.admin if side == "person" else h.person
        if data is not None:
            if shell and h.erlaubt and h.stand == "offen" and other is not None:
                with contextlib.suppress(Exception):
                    await other.send_bytes(data)
            continue
        try:
            m = clean(kinds, json.loads(raw or ""))
        except ValueError:
            m = None
        if m is None:
            continue
        if m["typ"] == "ende":
            await end(h, side)
            return
        if m["typ"] == "teilt":
            h.teilt = m["an"]
        if m["typ"] == "erlaubt":
            if h.stand != "offen" or h.erlaubt:
                continue
            log("erlaubt", "ja" if m["an"] else "nein", 1 if m["an"] else 0)
            if not m["an"]:
                await end(h, "abgelehnt")
                return
            h.erlaubt = True
        await _send(other, m)
    await end(h, side)


async def _clock(h):
    """The end of a help: HINWEIS_S before it the admin's page warns, at the end it closes."""
    while current() is h and h.stand == "offen":
        now = time.time()
        if now >= h.bis:
            await end(h, "zeit")
            return
        if not h.hinweis and h.bis - now <= HINWEIS_S:
            h.hinweis = True
            await _send(h.admin, {"typ": "hinweis", "rest": int(h.bis - now),
                                  "kann_verlaengern": h.bis - h.seit + 1 < max_min() * 60})
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(h.ende.wait(), 5)


async def _refuse(ws, why, code=4403):
    log("abgewiesen", why, 0)
    with contextlib.suppress(Exception):
        await ws.close(code)


@router.websocket("/api/hilfe/ws")
async def person_ws(ws: WebSocket):
    """The person's socket: Origin first, then her key in the first message (never in the address)."""
    if not admin_on():
        return await _refuse(ws, "aus", 4404)
    if not _same_origin(ws):
        guard.log("foreign_page_refused", path="/api/hilfe/ws")
        return await _refuse(ws, "fremde seite")
    if _notaus(count=True):
        return await _refuse(ws, "notaus", 4503)
    await ws.accept()
    try:
        raw = await asyncio.wait_for(ws.receive_text(), HALLO_S)
        m = json.loads(raw) if len(raw) < 512 else {}
    except Exception:
        m = {}
    h = current()
    tok = m.get("tok") if isinstance(m, dict) and m.get("typ") == "hallo" else None
    if h is None or h.stand != "wartet" or h.person is not None or not isinstance(tok, str) \
            or not re.fullmatch(r"[A-Za-z0-9_\-]{30,60}", tok) or not hmac.compare_digest(_h(tok), h.tok_h):
        return await _refuse(ws, "schluessel")
    if h.ende is None:
        h.ende = asyncio.Event()
    h.person = ws
    await _send(ws, {"typ": "stand", "stand": "wartet", "admin": h.admin_name})
    await _relay(h, "person", ws)


@router.websocket("/api/hilfe/shell")
async def person_shell(ws: WebSocket):
    """S3: the anchor program in the person's terminal. A program, no page: any Origin header is refused (no web page
    can open it). The number and the first name in the first message, checked like /api/hilfe/start."""
    if not admin_on():
        return await _refuse(ws, "aus", 4404)
    if ws.headers.get("origin") is not None:
        guard.log("foreign_page_refused", path="/api/hilfe/shell")
        return await _refuse(ws, "fremde seite")
    if _notaus(count=True):
        return await _refuse(ws, "notaus", 4503)
    try:
        guard.limit(ws, "spontanhilfe_start")
    except HTTPException:
        return await _refuse(ws, "gesperrt", 4429)
    await ws.accept()
    try:
        raw = await asyncio.wait_for(ws.receive_text(), HALLO_S)
        m = json.loads(raw) if len(raw) < 512 else {}
    except Exception:
        m = {}
    if not isinstance(m, dict) or m.get("typ") != "hallo":
        return await _refuse(ws, "schluessel")
    name = re.sub(r"\s+", " ", str(m.get("name") or "")).strip()
    nummer = str(m.get("nummer") or "").replace(" ", "")
    if not NAME.fullmatch(name):
        await _send(ws, {"typ": "fehler", "grund": "name"})
        return await _refuse(ws, "name")
    h = _pruefen(nummer, "")
    if h is None:
        await _send(ws, {"typ": "fehler", "grund": "nummer"})
        return await _refuse(ws, "schluessel")
    os_ = str(m.get("os") or "")
    h.name, h.stand, h.art, h.nummer = name, "wartet", "shell", ""
    h.os = os_ if OS.fullmatch(os_) else ""
    if h.ende is None:
        h.ende = asyncio.Event()
    h.person = ws
    _wo(h, ws)
    log("wartet", "shell", 1)
    _live("Spontanhilfe: eine Person wartet")
    t = asyncio.create_task(_melden(h))
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)
    await _send(ws, {"typ": "stand", "stand": "wartet", "admin": h.admin_name})
    await _relay(h, "person", ws)


@router.websocket("/api/spontanhilfe/admin")
async def admin_ws(ws: WebSocket):
    """The admin's socket: switch, Origin, admin login, Notaus, ticket of this login, then the help opens."""
    import fernzugang
    if not admin_on():
        return await _refuse(ws, "aus", 4404)
    if not _same_origin(ws):
        guard.log("foreign_page_refused", path="/api/spontanhilfe/admin")
        return await _refuse(ws, "fremde seite")
    if not fernzugang.is_admin_browser(ws):
        return await _refuse(ws, "kein admin")
    if _notaus(count=True):
        return await _refuse(ws, "notaus", 4503)
    raw = ws.query_params.get("t", "")
    tk = TICKETS.pop(_h(raw), None) if re.fullmatch(r"[A-Za-z0-9_\-]{30,60}", raw) else None
    h = current()
    if not tk or tk["until"] < time.time() or not hmac.compare_digest(tk["login"], fernzugang._login(ws)) \
            or h is None or tk["hid"] != h.id or h.stand != "wartet" or h.person is None:
        return await _refuse(ws, "ticket")
    await ws.accept()
    if h.ende is None:
        h.ende = asyncio.Event()
    h.admin, h.stand = ws, "offen"
    h.seit = time.time()
    h.bis = h.seit + min(START_MIN, max_min()) * 60
    STATS["hilfen"] = (STATS["hilfen"] + 1) if STATS["heute"] == time.strftime("%Y-%m-%d") else 1
    STATS["heute"] = time.strftime("%Y-%m-%d")
    log("sitzung_auf", h.art, 1)
    _live("Spontanhilfe geöffnet")
    if h.art == "shell":     # S3: her terminal asks once more; no bytes pass before her „j“ (no picture: no ICE)
        await _send(h.person, {"typ": "stand", "stand": "frage", "admin": h.admin_name, "bis": int(h.bis)})
        await _send(ws, {"typ": "stand", "stand": "offen", "art": "shell", "name": h.name, "bis": int(h.bis),
                         "kann_verlaengern": h.bis - h.seit + 1 < max_min() * 60})
    else:
        ice = _ice(h)
        await _send(h.person, {"typ": "stand", "stand": "offen", "admin": h.admin_name, "bis": int(h.bis), "ice": ice})
        await _send(ws, {"typ": "stand", "stand": "offen", "art": "ansehen", "name": h.name, "bis": int(h.bis), "ice": ice,
                         "kann_verlaengern": h.bis - h.seit + 1 < max_min() * 60})
    clock = asyncio.create_task(_clock(h))
    try:
        await _relay(h, "admin", ws)
    finally:
        clock.cancel()
