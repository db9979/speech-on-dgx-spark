"""KI-Dungeon-Master: Gäste mit E-Mail (plan dungeon-master Stufe 3 „Gast-Registrierung“, Dominik 2026-10-22 „Ok“ =
6-stelliger Code, nur der Hash der Adresse, Postfach wählt der Admin, 8 Helden; 2026-10-23 Speicherart „Hash, Adresse nur
bei Mail-Wunsch“). Own switch „dungeongast“ (chat.dungeon_gast, parent dungeon, off).

A guest at the table (only with a seat link, so only someone a profile invited) types its address; the panel sends a
6-digit code from the mailbox the admin picked (Funktionen → KI-Dungeon-Master → „Regeln anpassen“, card „Gäste mit
E-Mail“). With the code the guest gets its own guest account on this device and on any later one: up to HELDEN_MAX
heroes kept like a profile's, taken into every new round it is invited to.

What lies on the Spark (STATE/dungeon-gaeste.json, 0600):
  - per account only the HMAC of the address (key in the same file), the hashes of its device tokens, its heroes
  - the address itself only when the guest switches on „Du bist dran per Mail“, sealed like a password (vault.seal);
    switching it off, or deleting the account, removes it
  - a code: its hash, valid PIN_S, at most TRIES wrong tries, at most PRO_STUNDE codes an hour per address

Every mail is a fixed text of the panel (code, „Du bist dran“), never a model's or a player's words; at most TAG_MAX
mails a day in all, ZUG_TAG „Du bist dran“ per account and day, one per turn, only while the guest is not at the
table. The Notaus holds mails off. Logs: fixed words and numbers, never an address.

The look (Dominik 2026-10-25 „1-3 und 5 umsetzten“): next to the text part an HTML part like a page of the game,
inline styles only, no picture, nothing loaded from outside (no tracking), the colours of the round's world (FARBEN).
„Du bist dran“ may carry the narrator's last sentence (vorschau: at most VORSCHAU chars, no links, escaped; the host
switches it off at the table) and a button „Weiterspielen“: a one-time link (#weiter=<token>, WEITER_S, used once, only
its hash kept) that gives that device a fresh key for its seat (dungeon.weiter). No permanent seat key in any mail.
"""
import copy
import email.message
import email.policy
import email.utils
import hashlib
import hmac
import html
import os
import re
import secrets
import threading
import time

import features
import notaus
import vault
from common import STATE, read_json, write_json

FILE = os.path.join(STATE, "dungeon-gaeste.json")
PIN_S = 600                # a code is valid this long
TRIES = 5                  # wrong codes before it is gone
PRO_STUNDE = 3             # codes an hour for one address
TAG_MAX = 40               # mails a day in all (codes and „Du bist dran“)
KONTEN_MAX = 300           # guest accounts on the Spark
HELDEN_MAX = 8             # heroes per guest account
GERAETE = 5                # devices (tokens) per account; a sixth pushes out the oldest
ZUG_TAG = 3                # „Du bist dran“ mails per account and day
ZUG_NACH = 600             # seconds after a turn opened before its mail goes out (the guest may be at the table)
ADDR = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
                  r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+")
TOKEN = re.compile(r"[A-Za-z0-9_\-]{43}")
PIN = re.compile(r"[0-9]{6}")
WEITER_S = 12 * 3600       # a „Weiterspielen“ link of a mail is valid this long, and only once
VORSCHAU = 160             # chars of the narrator's last sentence in „Du bist dran“
_LINKISH = re.compile(r"(?i)\b(?:[a-z][a-z0-9+.-]*://|www\.)\S*|\S+@\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:[a-z]{2,24})(?:/\S*)?\b")
# per world (dungeon_regeln.json „welten“): page, ink, accent, sign; any other world reads as parchment
FARBEN = {"fantasy": ("#f4e9d0", "#3b2a1a", "#8a5a2b", "📜"), "horror": ("#1f1515", "#eadede", "#9b2226", "🕯"),
          "scifi": ("#e6edf3", "#16232f", "#2f6690", "🛰"), "piraten": ("#e2f0ea", "#14352d", "#1f7a63", "⚓")}
_lock = threading.Lock()
clock = time.time          # the one clock of this module (tests set it)

TEXTE = {
    "code": (("Dein Code für den Dungeon-Master", "Dein Code für „{titel}“: {pin}\n\nEr gilt 10 Minuten. Wenn du ihn nicht "
              "angefordert hast, lass diese Mail einfach liegen.\n"),
             ("Your code for the Dungeon Master", "Your code for \"{titel}\": {pin}\n\nIt is valid for 10 minutes. If you did "
              "not ask for it, just ignore this mail.\n")),
    "dran": (("Du bist dran: {titel}", "In „{titel}“ ist Zug {zug} offen und wartet auf {held}.\n\nÖffne deinen Platz-Link, "
              "um weiterzuspielen. Abbestellen: am Tisch unter „Gast-Konto“ „Du bist dran per Mail“ ausschalten.\n"),
             ("Your turn: {titel}", "In \"{titel}\" turn {zug} is open and waits for {held}.\n\nOpen your seat link to play "
              "on. To stop these mails: at the table under \"Guest account\" switch off \"Your turn by mail\".\n"))}
KNOPF = ("Weiterspielen", "Play on")
KNOPF_TEXT = ("Weiterspielen (einmal, {stunden} Stunden gültig): {link}\n", "Play on (once, valid for {stunden} hours): {link}\n")
ZULETZT = ("Zuletzt am Tisch", "Last at the table")


def on():
    return features.admin_on("dungeongast")


def _read():
    d = read_json(FILE, {})
    d = d if isinstance(d, dict) else {}
    for k in ("konten", "codes", "weiter"):
        d[k] = {a: v for a, v in (d.get(k) or {}).items() if isinstance(v, dict)} if isinstance(d.get(k), dict) else {}
    d["tag"] = d["tag"] if isinstance(d.get("tag"), dict) else {}
    return d


def _write(d):
    write_json(FILE, d, mode=0o600, dir_mode=0o700)


def _secret(d):
    if not re.fullmatch(r"[0-9a-f]{64}", str(d.get("geheim", ""))):
        d["geheim"] = secrets.token_hex(32)
    return bytes.fromhex(d["geheim"])


def _hash(d, s):
    return hmac.new(_secret(d), s.encode(), hashlib.sha256).hexdigest()[:40]


def norm(addr):
    a = str(addr or "").strip()
    if len(a) > 254 or not ADDR.fullmatch(a):
        raise ValueError("adresse")
    local, _, dom = a.rpartition("@")
    return f"{local}@{dom.lower()}"


def _day(d, now):
    t = time.strftime("%Y-%m-%d", time.localtime(now))
    if d["tag"].get("t") != t:
        d["tag"] = {"t": t, "mails": 0, "codes": 0, "dran": 0, "neu": 0, "falsch": 0}
    return d["tag"]


# ---------------------------------------------------------------- the admin's mailbox
def sender():
    """(profile id, mailbox) the admin picked to send from, or None (not picked, or gone, or without outgoing server)."""
    import mail
    a = _read().get("absender") or {}
    acct = next((x for x in mail.get(a.get("uid", ""))["accounts"] if x.get("id") == a.get("acct")), None) if a.get("uid") else None
    return (a["uid"], acct) if acct and _sends(acct) else None


def _sends(acct):
    """The mailbox has an outgoing server: typed in, or the known provider's (iCloud, Gmail, GMX, WEB.DE: senden.SMTP_FOR).
    Dominik 2026-10-24: an iCloud mailbox was missing from the choice, it has no own smtp_host."""
    import senden
    try:
        return bool(senden.outgoing(acct))
    except (ValueError, KeyError):
        return False


def choices():
    """The mailboxes with an outgoing server of every profile, for the admin's choice (name and address only)."""
    import mail
    import profiles
    out = []
    for p in profiles.names():
        for x in mail.get(p["id"])["accounts"]:
            if _sends(x):
                out.append({"k": f"{p['id']}/{x['id']}", "name": f"{p.get('name', '')} · {x['user']}"})
    return out


def admin_view():
    a = _read().get("absender") or {}
    return {"an": on(), "absender": f"{a['uid']}/{a['acct']}" if a.get("uid") else "", "bereit": bool(sender()),
            "postfaecher": choices(), **counts()}


def set_sender(k):
    """The admin's choice: "<profile id>/<mailbox id>" of choices(), or "" for none."""
    with _lock:
        d = _read()
        if not k:
            d.pop("absender", None)
        else:
            if k not in {x["k"] for x in choices()}:
                raise ValueError("postfach")
            uid, _, acct = k.partition("/")
            d["absender"] = {"uid": uid, "acct": acct}
        _write(d)
    print(f"dungeon: gastmail | absender {'gesetzt' if k else 'leer'}", flush=True)


_WARUM = (("no TLS", "kein tls"), ("not reachable", "nicht erreichbar"), ("user name or password", "anmeldung"),
          ("recipients", "empfaenger"), ("refused the mail", "abgelehnt"), ("broke off", "abbruch"))


def _why(e):
    """A fixed reason word for the journal (never the server's text or an address): why a mail did not go."""
    if isinstance(e, notaus.NotausAktiv):
        return "notaus"
    if isinstance(e, LookupError):
        return "kein postfach"
    t = str(e)
    return next((w for k, w in _WARUM if k in t), "ausgang fehlt" if "outgoing" in t else type(e).__name__)


def _send(to, kind, lang, **kw):
    """One fixed mail of the panel from the admin's mailbox (senden._smtp: TLS, netguard). Raises when it did not go."""
    import senden
    s = sender()
    if not s:
        raise LookupError("postfach")
    uid, acct = s
    notaus.stop("aktion", uid)
    senden._smtp(acct, message(acct["user"], to, kind, lang, **kw))


def teaser(text):
    """The narrator's last sentence for „Du bist dran“: no link, no address, at most VORSCHAU chars on a word's end."""
    t = " ".join(_LINKISH.sub(" ", str(text or "")).split())
    parts = [x for x in re.split(r"(?<=[.!?…])\s+", t) if len(x) > 2]
    t = parts[-1] if parts else ""
    if len(t) > VORSCHAU:
        t = t[:VORSCHAU].rsplit(" ", 1)[0].rstrip(",;:–-") + " …"
    return t


def message(sender_addr, to, kind, lang, welt="", vorschau="", link="", **kw):
    """The mail itself: the fixed text and, as its alternative, the same as a page of the game (inline styles only,
    nothing from outside, every value escaped). vorschau and link only for „Du bist dran“."""
    li = 1 if lang == "en" else 0
    subj, text = TEXTE[kind][li]
    msg = email.message.EmailMessage(policy=email.policy.SMTP)
    msg["From"] = email.utils.formataddr(("Dungeon-Master", sender_addr))
    msg["To"] = to
    msg["Subject"] = subj.format(**kw)
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=sender_addr.rpartition("@")[2] or None)
    msg["Auto-Submitted"] = "auto-generated"
    vorschau = teaser(vorschau) if kind == "dran" else ""
    link = link if kind == "dran" and re.fullmatch(r"https?://[A-Za-z0-9.\-]+(?::\d{1,5})?/#weiter=[A-Za-z0-9_\-]{43}", link or "") else ""
    body = text.format(**kw)
    plain = (f"{ZULETZT[li]}: „{vorschau}“\n\n" if vorschau else "") + body \
        + ("\n" + KNOPF_TEXT[li].format(stunden=WEITER_S // 3600, link=link) if link else "")
    msg.set_content(plain)
    page, ink, accent, sign = FARBEN.get(welt, FARBEN["fantasy"])
    e = html.escape
    paras = "".join(f'<p style="margin:0 0 12px 0">{e(x).replace(chr(10), "<br>")}</p>' for x in body.strip().split("\n\n"))
    if kind == "code":
        paras = paras.replace(e(kw["pin"]), f'<b style="font-size:26px;letter-spacing:4px">{e(kw["pin"])}</b>', 1)
    quote = (f'<p style="margin:0 0 16px 0;padding:10px 14px;border-left:3px solid {accent};font-style:italic">'
             f'<span style="font-size:12px;font-style:normal;opacity:.75">{e(ZULETZT[li])}</span><br>{e(vorschau)}</p>') if vorschau else ""
    button = (f'<p style="margin:18px 0 6px 0"><a href="{e(link, quote=True)}" style="display:inline-block;padding:10px 22px;'
              f'background:{accent};color:{page};text-decoration:none;border-radius:6px;font-weight:bold">{e(KNOPF[li])}</a></p>'
              f'<p style="margin:0;font-size:12px;opacity:.75">{e(KNOPF_TEXT[li].split(":")[0].strip())}</p>') if link else ""
    msg.add_alternative(
        f'<!doctype html><html lang="{"en" if li else "de"}"><head><meta charset="utf-8"></head>'
        f'<body style="margin:0;padding:24px 12px;background:{page};color:{ink}">'
        f'<div style="max-width:520px;margin:0 auto;padding:22px 24px;border:2px solid {accent};border-radius:10px;'
        f'font-family:Georgia,\'Times New Roman\',serif;font-size:16px;line-height:1.5">'
        f'<div style="font-size:20px;font-weight:bold;color:{accent};margin:0 0 14px 0">{sign} {e(msg["Subject"])}</div>'
        f'{quote}{paras}{button}</div></body></html>', subtype="html")
    return msg


# ---------------------------------------------------------------- code and account
def ask_code(addr, titel, lang, now=None, welt=""):
    """A 6-digit code to the address (hash kept, never the address). Silent about whether an account exists."""
    if not on():
        raise LookupError("aus")
    now = clock() if now is None else now
    a = norm(addr)
    pin = f"{secrets.randbelow(10 ** 6):06d}"
    with _lock:
        d = _read()
        day = _day(d, now)
        if day["mails"] >= TAG_MAX:
            raise OverflowError("mails")
        h = _hash(d, a)
        c = d["codes"].get(h) or {}
        sent = [t for t in c.get("sent") or [] if now - t < 3600]
        if len(sent) >= PRO_STUNDE:
            raise OverflowError("codes")
        d["codes"] = {k: v for k, v in d["codes"].items() if now - max(v.get("sent") or [0]) < 3600}
        d["codes"][h] = {"pin": _hash(d, "pin:" + h + ":" + pin), "until": now + PIN_S, "tries": 0, "sent": sent + [now]}
        day["mails"] += 1
        day["codes"] += 1
        _write(d)
    try:
        _send(a, "code", lang, titel=titel[:80], pin=pin, welt=welt)
    except Exception as e:      # noqa: BLE001 - the guest gets the reason word, the journal a fixed line
        print(f"dungeon: gastmail | code nicht gesendet | {_why(e)}", flush=True)
        if isinstance(e, notaus.NotausAktiv):
            raise PermissionError("notaus")
        if isinstance(e, LookupError):            # no mailbox picked: say so, not „try again“ (Dominik 2026-10-24 screenshot)
            raise LookupError("postfach")
        raise ConnectionError("mail")
    print("dungeon: gastmail | code gesendet", flush=True)


def login(addr, pin, now=None):
    """The code typed back: the account (made the first time) and a new device token, shown once."""
    if not on():
        raise LookupError("aus")
    now = clock() if now is None else now
    a = norm(addr)
    if not PIN.fullmatch(str(pin or "")):
        raise ValueError("code")
    with _lock:
        d = _read()
        day = _day(d, now)
        h = _hash(d, a)
        c = d["codes"].get(h)
        if not c or c.get("until", 0) < now or c.get("tries", 0) >= TRIES:
            raise PermissionError("code")
        if not hmac.compare_digest(c["pin"], _hash(d, "pin:" + h + ":" + str(pin))):
            c["tries"] = c.get("tries", 0) + 1
            day["falsch"] += 1
            _write(d)
            print("dungeon: gastmail | code falsch", flush=True)
            raise PermissionError("code")
        d["codes"].pop(h)
        kid = next((k for k, v in d["konten"].items() if hmac.compare_digest(v.get("a", ""), h)), None)
        if not kid:
            if len(d["konten"]) >= KONTEN_MAX:
                raise OverflowError("konten")
            kid = "g" + os.urandom(5).hex()
            d["konten"][kid] = {"a": h, "helden": [], "tok": [], "made": int(now)}
            day["neu"] += 1
        tok = secrets.token_urlsafe(32)
        k = d["konten"][kid]
        k["tok"] = (k.get("tok") or [])[-(GERAETE - 1):] + [_hash(d, "tok:" + tok)]
        k["last"] = int(now)
        _write(d)
    print("dungeon: gastmail | angemeldet", flush=True)
    return tok


def _find(d, tok):
    if not isinstance(tok, str) or not TOKEN.fullmatch(tok):
        return None, None
    th = _hash(d, "tok:" + tok)
    for kid, k in d["konten"].items():
        if any(hmac.compare_digest(th, x) for x in k.get("tok") or []):
            return kid, k
    return None, None


def account(tok):
    """(account id, account) of a device token, or raises PermissionError."""
    with _lock:
        kid, k = _find(_read(), tok)
    if not kid:
        raise PermissionError("konto")
    return kid, copy.deepcopy(k)


def heroes(kid):
    with _lock:
        k = _read()["konten"].get(kid) or {}
    return copy.deepcopy(k.get("helden") or [])


def keep(kid, h):
    """A guest account's hero after a turn (by hid); a new one only while there is room. True when kept."""
    with _lock:
        d = _read()
        k = d["konten"].get(kid)
        if not k:
            return False
        hs = k.setdefault("helden", [])
        for i, x in enumerate(hs):
            if x.get("hid") == h.get("hid"):
                hs[i] = copy.deepcopy(h)
                break
        else:
            if len(hs) >= HELDEN_MAX:
                return False
            hs.append(copy.deepcopy(h))
        _write(d)
    return True


def drop_hero(kid, hid):
    with _lock:
        d = _read()
        k = d["konten"].get(kid)
        if not k or not any(x.get("hid") == hid for x in k.get("helden") or []):
            raise LookupError("held")
        k["helden"] = [x for x in k["helden"] if x.get("hid") != hid]
        _write(d)
    print("dungeon: gastmail | held geloescht", flush=True)


def turn_mail(kid, an, addr=""):
    """„Du bist dran per Mail“: on needs the address again (it must be the account's), kept sealed; off removes it."""
    with _lock:
        d = _read()
        k = d["konten"].get(kid)
        if not k:
            raise PermissionError("konto")
        if an:
            a = norm(addr)
            if not hmac.compare_digest(k["a"], _hash(d, a)):
                raise ValueError("adresse")
            k["seal"] = vault.seal(a)
        else:
            k.pop("seal", None)
        _write(d)
    print(f"dungeon: gastmail | zugmail {'an' if an else 'aus'}", flush=True)


def forget(kid):
    """The guest's whole account: heroes, devices, the sealed address."""
    with _lock:
        d = _read()
        d["konten"].pop(kid, None)
        _write(d)
    print("dungeon: gastmail | konto geloescht", flush=True)


def view(kid, k, rules, hero_view, lang):
    return {"helden": [hero_view(rules, h, lang, full=False) for h in k.get("helden") or []], "helden_max": HELDEN_MAX,
            "zugmail": bool(k.get("seal"))}


# ---------------------------------------------------------------- „Du bist dran“
def due(rd, now, seen):
    """The guest seats of a running round that get „Du bist dran“ now: an account with the mail on, not acted, the turn
    open ZUG_NACH, not at the table (seen: pid → last poll), once per turn. Marks them in rd["gastmail"]."""
    if not on() or rd.get("status") != "laeuft" or rd.get("dm") or now - rd.get("zug_t", now) < ZUG_NACH:
        return []
    sent = rd.setdefault("gastmail", {})
    out = []
    for pid, p in rd["plaetze"].items():
        if p.get("konto") and p.get("held") and pid not in rd["offen"] and sent.get(pid) != rd["zug"] \
                and now - seen.get(pid, 0) > ZUG_NACH:
            sent[pid] = rd["zug"]
            out.append((p["konto"], p["held"]["name"], pid))
    return out


def send_turns(rd, todo, now=None):
    """The „Du bist dran“ mails (blocking; called in a thread), each with a one-time „Weiterspielen“ link when the round
    knows the panel's address (rd["base"]) and, unless the host switched it off, the narrator's last sentence. Never raises."""
    now = clock() if now is None else now
    vorschau = next((e.get("text", "") for e in reversed(rd.get("log") or []) if e.get("art") == "dm"), "") \
        if rd.get("mail_vorschau", True) else ""
    for kid, held, pid in todo:
        with _lock:
            d = _read()
            k = d["konten"].get(kid)
            day = _day(d, now)
            n = k.setdefault("dran", {}) if k else {}
            if not k or not k.get("seal") or day["mails"] >= TAG_MAX or (n.get("t") == day["t"] and n.get("n", 0) >= ZUG_TAG):
                print("dungeon: gastmail | dran | uebersprungen", flush=True)
                continue
            addr = vault.open_(k["seal"])
            k["dran"] = {"t": day["t"], "n": (n.get("n", 0) if n.get("t") == day["t"] else 0) + 1}
            link = ""
            if rd.get("base") and rd.get("rid"):
                tok = secrets.token_urlsafe(32)
                d["weiter"] = {h: w for h, w in d["weiter"].items() if w.get("until", 0) > now}
                d["weiter"][_hash(d, "weiter:" + tok)] = {"kid": kid, "rid": rd["rid"], "pid": pid, "until": now + WEITER_S}
                link = f"{rd['base']}/#weiter={tok}"
            day["mails"] += 1
            day["dran"] += 1
            _write(d)
        try:
            _send(addr, "dran", rd.get("lang", "de"), titel=rd.get("titel", "")[:80], zug=rd.get("zug", 0), held=held,
                  welt=rd.get("welt", ""), vorschau=vorschau, link=link)
            print("dungeon: gastmail | dran | gesendet", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"dungeon: gastmail | dran | nicht gesendet | {_why(e)}", flush=True)


def redeem(tok, now=None):
    """A „Weiterspielen“ link opened: (account, round, seat) once, while WEITER_S holds; else PermissionError."""
    now = clock() if now is None else now
    if not isinstance(tok, str) or not TOKEN.fullmatch(tok):
        raise PermissionError("weiter")
    with _lock:
        d = _read()
        w = d["weiter"].pop(_hash(d, "weiter:" + tok), None)
        d["weiter"] = {h: x for h, x in d["weiter"].items() if x.get("until", 0) > now}
        _write(d)
    if not w or w.get("until", 0) <= now or w.get("kid") not in _read()["konten"]:
        print("dungeon: gastmail | weiter | abgelehnt", flush=True)
        raise PermissionError("weiter")
    print("dungeon: gastmail | weiter | eingeloest", flush=True)
    return w["kid"], w["rid"], w["pid"]


def counts():
    """Numbers only (Live, admin card)."""
    d = _read()
    t = d["tag"] if d["tag"].get("t") == time.strftime("%Y-%m-%d", time.localtime(clock())) else {}
    return {"konten": len(d["konten"]), "zugmail": sum(1 for k in d["konten"].values() if k.get("seal")),
            "helden": sum(len(k.get("helden") or []) for k in d["konten"].values()),
            "codes_heute": t.get("codes", 0), "mails_heute": t.get("mails", 0), "neu_heute": t.get("neu", 0)}
