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
"""
import copy
import email.message
import email.policy
import email.utils
import hashlib
import hmac
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


def on():
    return features.admin_on("dungeongast")


def _read():
    d = read_json(FILE, {})
    d = d if isinstance(d, dict) else {}
    for k in ("konten", "codes"):
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
    return (a["uid"], acct) if acct and acct.get("smtp_host") else None


def choices():
    """The mailboxes with an outgoing server of every profile, for the admin's choice (name and address only)."""
    import mail
    import profiles
    out = []
    for p in profiles.names():
        for x in mail.public(p["id"])["accounts"]:
            if x.get("smtp"):
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


def _send(to, kind, lang, **kw):
    """One fixed mail of the panel from the admin's mailbox (senden._smtp: TLS, netguard). Raises when it did not go."""
    import senden
    s = sender()
    if not s:
        raise LookupError("postfach")
    uid, acct = s
    notaus.stop("aktion", uid)
    subj, text = TEXTE[kind][1 if lang == "en" else 0]
    msg = email.message.EmailMessage(policy=email.policy.SMTP)
    msg["From"] = email.utils.formataddr(("Dungeon-Master", acct["user"]))
    msg["To"] = to
    msg["Subject"] = subj.format(**kw)
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=acct["user"].rpartition("@")[2] or None)
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(text.format(**kw))
    senden._smtp(acct, msg)


# ---------------------------------------------------------------- code and account
def ask_code(addr, titel, lang, now=None):
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
        _send(a, "code", lang, titel=titel[:80], pin=pin)
    except Exception as e:      # noqa: BLE001 - the guest gets the reason word, the journal a fixed line
        print(f"dungeon: gastmail | code nicht gesendet | {type(e).__name__}", flush=True)
        if isinstance(e, notaus.NotausAktiv):
            raise PermissionError("notaus")
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
            out.append((p["konto"], p["held"]["name"]))
    return out


def send_turns(rd, todo, now=None):
    """The „Du bist dran“ mails (blocking; called in a thread). Never raises."""
    now = clock() if now is None else now
    for kid, held in todo:
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
            day["mails"] += 1
            day["dran"] += 1
            _write(d)
        try:
            _send(addr, "dran", rd.get("lang", "de"), titel=rd.get("titel", "")[:80], zug=rd.get("zug", 0), held=held)
            print("dungeon: gastmail | dran | gesendet", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"dungeon: gastmail | dran | nicht gesendet | {type(e).__name__}", flush=True)


def counts():
    """Numbers only (Live, admin card)."""
    d = _read()
    t = d["tag"] if d["tag"].get("t") == time.strftime("%Y-%m-%d", time.localtime(clock())) else {}
    return {"konten": len(d["konten"]), "zugmail": sum(1 for k in d["konten"].values() if k.get("seal")),
            "helden": sum(len(k.get("helden") or []) for k in d["konten"].values()),
            "codes_heute": t.get("codes", 0), "mails_heute": t.get("mails", 0), "neu_heute": t.get("neu", 0)}
