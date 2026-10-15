"""Telefon → Ich (plan plaene/telefon-anruf.md, Stufe T2): what each profile sets up for itself under Ich → Telefon.

    Meine Rufnummern   the profile's own mobile and landline numbers. A number counts only once it is confirmed:
                       the page shows a code of CODE_LEN digits, the person calls the Spark from that number
                       and types it (telefon.Call.confirm_number). So nobody can put someone else's number on
                       their profile; a number belongs to at most one profile. Calls from outside use them from
                       stage T3 on; T2 only confirms.
    Telefon-PIN        PIN_MIN to PIN_MAX digits, typed on the phone and ended with #, never spoken. On a handset
                       assigned to the profile it stands for the voice when the voice is not sure; on a shared
                       phone it picks the profile whose PIN it is. FAILS wrong PINs in FAIL_WINDOW at one phone:
                       no PIN there for LOCK seconds and a notification to the handset's profile. Stored as a
                       salted PBKDF2 hash in the vault, never sent back, never in a log, the history or a model.
                       Changing it needs a fresh code (stufen.LIST).
    Meine Mobilteile   the internal handsets the admin assigned to the profile (read only here).
    Meine Telefonate   the profile's calls: when, how long, how many questions, of which kind (no number, no
                       words; the questions themselves are in the profile's history). Delete one or all.

    Anrufe vom Spark   (T4, telefon_anruf.py) the preference "Der Spark darf mich anrufen" and the calls the profile
                       ordered (Weckruf, Erinnerung): see and delete.

    users/<id>/telefon.json  {"nummern": [{"id", "nr" (vault), "name", "ok", "code" (vault), "bis", "t"}],
                              "pin" (vault: {"salt", "hash"}), "anrufe": [{"id", "t", "s", "fragen", "art"}],
                              "geplant": [{"id", "t", "art", "text"}], "heute": {"d", "n"} (calls from the Spark today)}

The wrong PINs and codes are counted in memory per phone number (hashed), like the code word at a speaker
(spkcode.py). Everything here is part of "Den Spark anrufen" (features.py "telefon"): no switch of its own.
"""
import hashlib
import hmac
import json
import re
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import profiles
import telefon
import vault
from core import assistant, browser_profile, json_body, secret_profile, secret_profile_fresh

router = APIRouter()

MAX_NUMBERS = 5
CODE_LEN = 4
CODE_SECONDS = 15 * 60          # a confirmation code counts this long
CODE_TRIES = 3                  # wrong codes before the code is void
PIN_MIN, PIN_MAX = 4, 8
FAIL_WINDOW = 15 * 60
FAILS = 3                       # wrong PINs at one phone in FAIL_WINDOW ...
LOCK = 30 * 60                  # ... and no PIN there for this long
KEEP_CALLS = 50
ROUNDS = 100_000                # PBKDF2 rounds of the PIN hash
ARTEN = ("intern", "gemeinsam", "extern", "bestaetigung", "spark")
PLAN_MAX = 10                   # calls a profile has ordered and that are still to come (telefon_anruf.py)
PLAN_ARTEN = ("weckruf", "erinnerung")

_lock = threading.Lock()
_fails = {}                     # hashed phone number -> [times]
_locked = {}                    # hashed phone number -> until


def _file(uid):
    return profiles._path(uid, "telefon.json")


def _read(uid):
    from common import read_json
    d = read_json(_file(uid), {})
    return d if isinstance(d, dict) else {}


def _write(uid, d):
    profiles._write(_file(uid), d)


def canon(nr):
    """A number as the PBX shows it, in one form: digits with a leading + for the international form ("0049…" and
    "+49…" alike); "" when it is no phone number."""
    n = telefon.clean_number(nr).replace("*", "").replace("#", "")
    plus = n.startswith("+") or n.startswith("00")
    digits = re.sub(r"\D", "", n)
    if plus and n.startswith("00"):
        digits = digits[2:]
    if not 5 <= len(digits) <= 17:
        return ""
    return ("+" if plus else "") + digits


def same(a, b):
    """Whether two numbers are the same line: equal, or one national ("0170…") and one international ("+49170…")
    with only a country code (1 to 3 digits) in front."""
    a, b = canon(a), canon(b)
    if not a or not b:
        return False
    if a == b:
        return True
    for x, y in ((a, b), (b, a)):
        if x.startswith("0") and not x.startswith("00") and y.startswith("+") and y.endswith(x[1:]) \
                and 1 <= len(y) - len(x) <= 3:
            return True
    return False


def _key(nr):
    """The phone number as a counter key: hashed, so memory holds no number."""
    return hashlib.sha256(("telefon:" + canon(nr)).encode()).hexdigest()[:24]


def _plain(entry, k):
    return vault.open_(entry.get(k) or "") or ""


# ---------------------------------------------------------------- own numbers
def numbers(uid):
    return [x for x in _read(uid).get("nummern", []) if isinstance(x, dict) and x.get("id")]


def _all_numbers():
    for uid in profiles.user_ids():
        for e in numbers(uid):
            yield uid, e


def owner_of(nr):
    """The profile whose confirmed number this is ("" when none)."""
    return next((uid for uid, e in _all_numbers() if e.get("ok") and same(_plain(e, "nr"), nr)), "")


def pending_for(nr, now=None):
    """The profile waiting to confirm this number with a code that still counts ("" when none)."""
    now = time.time() if now is None else now
    return next((uid for uid, e in _all_numbers()
                 if not e.get("ok") and e.get("code") and e.get("bis", 0) > now and same(_plain(e, "nr"), nr)), "")


def add_number(uid, nr, name="", now=None):
    """A new own number (or a new code for one not confirmed yet); returns the code. ValueError with the reason."""
    now = time.time() if now is None else now
    c = canon(nr)
    if not c:
        raise ValueError("Bitte eine Rufnummer mit Vorwahl eintragen, z. B. 0170 1234567.")
    if telefon.internal(c):
        raise ValueError("Interne Nummern der Telefonanlage ordnet der Admin zu (Funktionen → Den Spark anrufen).")
    other = owner_of(c)
    if other and other != uid:
        raise ValueError("Diese Nummer ist schon bei einem anderen Profil bestätigt.")
    name = re.sub(r"[\x00-\x1f<>\"\\]", "", str(name or "")).strip()[:40]
    code = "".join(secrets.choice("0123456789") for _ in range(CODE_LEN))
    with _lock:
        d = _read(uid)
        nn = [e for e in d.get("nummern", []) if isinstance(e, dict)]
        hit = next((e for e in nn if same(_plain(e, "nr"), c)), None)
        if hit and hit.get("ok"):
            raise ValueError("Diese Nummer ist schon bestätigt.")
        if not hit:
            if len(nn) >= MAX_NUMBERS:
                raise ValueError(f"Höchstens {MAX_NUMBERS} Rufnummern.")
            hit = {"id": secrets.token_hex(4), "nr": vault.seal(c), "ok": False, "t": int(now)}
            nn.append(hit)
        hit.update(name=name or hit.get("name", ""), code=vault.seal(code), bis=int(now + CODE_SECONDS), versuche=0)
        d["nummern"] = nn
        _write(uid, d)
    return code


def try_code(nr, entered, now=None):
    """A code typed on a call from nr: "ok" (the number is now confirmed), "wrong", "void" (too many wrong: the code
    no longer counts) or "none" (no code waits for this number)."""
    now = time.time() if now is None else now
    uid = pending_for(nr, now)
    if not uid:
        return "none", ""
    with _lock:
        d = _read(uid)
        e = next((x for x in d.get("nummern", []) if isinstance(x, dict) and not x.get("ok") and same(_plain(x, "nr"), nr)), None)
        if not e:
            return "none", ""
        if hmac.compare_digest(_plain(e, "code"), re.sub(r"\D", "", str(entered or ""))[:CODE_LEN + 4]):
            e.update(ok=True, code="", bis=0, versuche=0, seit=int(now))
            _write(uid, d)
            res = "ok"
        else:
            e["versuche"] = int(e.get("versuche", 0)) + 1
            if e["versuche"] >= CODE_TRIES:
                e.update(code="", bis=0)
            _write(uid, d)
            return ("void" if not e.get("code") else "wrong"), uid
    # the same number waiting at another profile no longer can be confirmed there
    for other in profiles.user_ids():
        if other != uid:
            with _lock:
                od = _read(other)
                keep = [x for x in od.get("nummern", []) if not (isinstance(x, dict) and not x.get("ok") and same(_plain(x, "nr"), nr))]
                if len(keep) != len(od.get("nummern", [])):
                    od["nummern"] = keep
                    _write(other, od)
    return res, uid


def remove_number(uid, nid):
    with _lock:
        d = _read(uid)
        nn = [e for e in d.get("nummern", []) if isinstance(e, dict) and e.get("id") != nid]
        if len(nn) == len(d.get("nummern", [])):
            return False
        d["nummern"] = nn
        _write(uid, d)
    return True


# ---------------------------------------------------------------- PIN
def _pin(uid):
    try:
        p = json.loads(vault.open_(_read(uid).get("pin") or "") or "null")
    except ValueError:
        return None
    return p if isinstance(p, dict) and p.get("hash") else None


def has_pin(uid):
    return bool(uid) and _pin(uid) is not None


def _hash(pin, salt):
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), ROUNDS).hex()


def set_pin(uid, pin):
    """Sets the Telefon-PIN ("" removes it). ValueError when it is not PIN_MIN to PIN_MAX digits or too simple."""
    pin = str(pin or "").strip()
    if pin and (not re.fullmatch(rf"\d{{{PIN_MIN},{PIN_MAX}}}", pin) or len(set(pin)) == 1
                or pin in "0123456789012345" or pin in "9876543210987654"):
        raise ValueError(f"Die PIN braucht {PIN_MIN} bis {PIN_MAX} Ziffern, nicht alle gleich und nicht der Reihe nach.")
    with _lock:
        d = _read(uid)
        d.pop("pin", None)
        if pin:
            salt = secrets.token_hex(16)
            d["pin"] = vault.seal(json.dumps({"salt": salt, "hash": _hash(pin, salt)}))
        _write(uid, d)
    return has_pin(uid)


def _pin_right(uid, entered):
    p = _pin(uid)
    try:
        return bool(p) and hmac.compare_digest(p["hash"], _hash(entered, p["salt"]))
    except (KeyError, ValueError, TypeError):
        return False


def locked(nr, now=None):
    now = time.time() if now is None else now
    return _locked.get(_key(nr), 0) > now


def pin_attempt(nr, uids, entered, now=None):
    """A PIN typed at the phone nr for one of uids (the handset's profile, or every profile at a shared phone):
    ("ok", uid) / ("wrong", "") / ("locked", "neu") when this one locked it / ("locked", "") while it is locked /
    ("none", "") when none of them has a PIN."""
    now = time.time() if now is None else now
    entered = re.sub(r"\D", "", str(entered or ""))[:PIN_MAX]
    have = [u for u in uids if has_pin(u)]
    if not have:
        return "none", ""
    k = _key(nr)
    with _lock:
        if _locked.get(k, 0) > now:
            return "locked", ""
    hits = [u for u in have if _pin_right(u, entered)]
    with _lock:
        if len(hits) == 1:
            _fails.pop(k, None)
            return "ok", hits[0]
        fails = [t for t in _fails.get(k, []) if now - t < FAIL_WINDOW] + [now]
        _fails[k] = fails[-10:]
        if len(_fails) > 1000:
            _fails.clear()
        if len(fails) >= FAILS:
            _locked[k] = now + LOCK
            return "locked", "neu"
    return "wrong", ""


# ---------------------------------------------------------------- calls
def keep_call(uid, t, secs, questions, art):
    with _lock:
        d = _read(uid)
        rows = [r for r in d.get("anrufe", []) if isinstance(r, dict)]
        rows.append({"id": secrets.token_hex(4), "t": int(t), "s": int(secs), "fragen": int(questions),
                     "art": art if art in ARTEN else "intern"})
        d["anrufe"] = rows[-KEEP_CALLS:]
        _write(uid, d)


def calls(uid):
    return [r for r in _read(uid).get("anrufe", []) if isinstance(r, dict)]


def drop_calls(uid, aid=""):
    with _lock:
        d = _read(uid)
        rows = [r for r in d.get("anrufe", []) if isinstance(r, dict) and aid and r.get("id") != aid]
        n = len(d.get("anrufe", [])) - len(rows)
        d["anrufe"] = rows
        _write(uid, d)
    return n


# ---------------------------------------------------------------- calls the profile ordered (T4, telefon_anruf.py)
def planned(uid):
    return sorted((r for r in _read(uid).get("geplant", []) if isinstance(r, dict) and r.get("art") in PLAN_ARTEN),
                  key=lambda r: r.get("t", 0))


def plan_add(uid, t, art, text):
    """A wake-up call or reminder by call at t (epoch seconds); ValueError("voll") with PLAN_MAX to come."""
    with _lock:
        d = _read(uid)
        rows = [r for r in d.get("geplant", []) if isinstance(r, dict)]
        if len(rows) >= PLAN_MAX:
            raise ValueError("voll")
        row = {"id": secrets.token_hex(4), "t": int(t), "art": art if art in PLAN_ARTEN else "erinnerung",
               "text": re.sub(r"[\x00-\x1f<>]", " ", str(text or ""))[:120].strip()}
        d["geplant"] = rows + [row]
        _write(uid, d)
    return row


def plan_drop(uid, pid=""):
    """Removes one ordered call (pid) or all; the number removed."""
    with _lock:
        d = _read(uid)
        old = [r for r in d.get("geplant", []) if isinstance(r, dict)]
        d["geplant"] = [r for r in old if pid and r.get("id") != pid]
        _write(uid, d)
    return len(old) - len(d["geplant"])


def day_calls(uid, day, add=0):
    """How many calls the Spark placed to the profile on day ("YYYY-MM-DD"), after adding add."""
    with _lock:
        d = _read(uid)
        h = d.get("heute") if isinstance(d.get("heute"), dict) and d["heute"].get("d") == day else {"d": day, "n": 0}
        if add:
            h["n"] = int(h.get("n", 0)) + add
            d["heute"] = h
            _write(uid, d)
    return int(h.get("n", 0))


def count(uid):
    """features.OWN: what the profile keeps here (numbers, PIN, calls, ordered calls)."""
    return len(numbers(uid)) + int(has_pin(uid)) + len(calls(uid)) + len(planned(uid))


def clear(uid):
    with _lock:
        _write(uid, {})


features.OWN["telefon"] = (count, clear)


def view(uid, now=None):
    now = time.time() if now is None else now
    out = []
    for e in numbers(uid):
        row = {"id": e["id"], "nr": _plain(e, "nr"), "name": e.get("name", ""), "ok": bool(e.get("ok"))}
        if not e.get("ok"):
            live = bool(e.get("code")) and e.get("bis", 0) > now
            row.update(code=_plain(e, "code") if live else "", bis=e.get("bis", 0) if live else 0)
        out.append(row)
    hs = [{"nr": n, "name": x.get("name", "")} for n, x in sorted(telefon.nummern().items()) if x.get("uid") == uid]
    return {"on": features.allowed("telefon", uid), "nummern": out, "pin": has_pin(uid), "mobilteile": hs,
            "anrufe": list(reversed(calls(uid))), "max": MAX_NUMBERS, "pin_len": [PIN_MIN, PIN_MAX],
            "code_min": CODE_SECONDS // 60, "angemeldet": telefon.signed_in(),
            "anrufen": features.reason("telefonanrufen", uid) in (None, "profile"), "anrufbar": features.pref_on("telefonanrufen", uid),
            "geplant": [{"id": r["id"], "t": r["t"], "art": r["art"], "text": r.get("text", "")} for r in planned(uid)]}


# ---------------------------------------------------------------- Ich → Telefon
def _on(uid):
    if not features.allowed("telefon", uid):
        raise HTTPException(403, ("„Den Spark anrufen“ geht für dich gerade nicht. " + features.missing_text("telefon", uid)).strip())


@router.get("/api/profile/telefon", dependencies=[Depends(assistant)])
def profile_get(request: Request, prof=Depends(browser_profile)):
    guard.limit(request, "telefon", prof["id"])
    return view(prof["id"])


# a new own number is a new way to reach the profile: a confirmed code (stufen.py)
@router.post("/api/profile/telefon/nummern", dependencies=[Depends(assistant)])
async def profile_add_number(request: Request, prof=Depends(secret_profile)):
    uid = prof["id"]
    guard.limit(request, "telefonich", uid)
    _on(uid)
    b = await json_body(request, 1024)
    try:
        add_number(uid, b.get("nr"), b.get("name", ""))
    except ValueError as e:
        print(f"telefon: rufnummer nicht eingetragen fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(400, str(e))
    print(f"telefon: rufnummer eingetragen fuer {profiles.log_name(prof)}, code wartet", flush=True)
    return view(uid)


@router.delete("/api/profile/telefon/nummern/{nid}", dependencies=[Depends(assistant)])
def profile_remove_number(nid: str, request: Request, prof=Depends(browser_profile)):
    guard.limit(request, "telefonich", prof["id"])
    if not remove_number(prof["id"], nid):
        print(f"telefon: rufnummer nicht gefunden fuer {profiles.log_name(prof)}", flush=True)
        raise HTTPException(404, "Diese Rufnummer gibt es nicht.")
    print(f"telefon: rufnummer entfernt fuer {profiles.log_name(prof)}", flush=True)
    return view(prof["id"])


# the PIN is protection itself: always a fresh code (stufen.py)
@router.put("/api/profile/telefon/pin", dependencies=[Depends(assistant)])
async def profile_pin(request: Request, prof=Depends(secret_profile_fresh)):
    uid = prof["id"]
    guard.limit(request, "telefonich", uid)
    _on(uid)
    b = await json_body(request, 256)
    if not str(b.get("pin") or ""):
        raise HTTPException(400, "Bitte eine PIN eingeben (zum Entfernen „PIN entfernen“).")
    try:
        set_pin(uid, b.get("pin"))
    except ValueError as e:
        print(f"telefon: pin nicht gesetzt fuer {profiles.log_name(prof)}, zu einfach", flush=True)
        raise HTTPException(400, str(e))
    guard.log("telefon_pin_set", ip=guard.client_ip(request), name=prof["name"], uid=uid)
    print(f"telefon: pin gesetzt fuer {profiles.log_name(prof)}", flush=True)
    return view(uid)


@router.delete("/api/profile/telefon/pin", dependencies=[Depends(assistant)])
def profile_pin_remove(request: Request, prof=Depends(browser_profile)):
    guard.limit(request, "telefonich", prof["id"])
    set_pin(prof["id"], "")
    guard.log("telefon_pin_removed", ip=guard.client_ip(request), name=prof["name"], uid=prof["id"])
    print(f"telefon: pin entfernt fuer {profiles.log_name(prof)}", flush=True)
    return view(prof["id"])


@router.delete("/api/profile/telefon/geplant", dependencies=[Depends(assistant)])
def profile_planned_clear(request: Request, id: str = "", prof=Depends(browser_profile)):
    """Deletes one ordered call (?id=) or all."""
    guard.limit(request, "telefonich", prof["id"])
    n = plan_drop(prof["id"], re.sub(r"[^0-9a-f]", "", id)[:8])
    print(f"telefon: {n} geplante anrufe geloescht fuer {profiles.log_name(prof)}", flush=True)
    return view(prof["id"])


@router.delete("/api/profile/telefon/anrufe", dependencies=[Depends(assistant)])
def profile_calls_clear(request: Request, id: str = "", prof=Depends(browser_profile)):
    """Deletes one call (?id=) or all."""
    guard.limit(request, "telefonich", prof["id"])
    n = drop_calls(prof["id"], re.sub(r"[^0-9a-f]", "", id)[:8])
    print(f"telefon: {n} telefonate geloescht fuer {profiles.log_name(prof)}", flush=True)
    return view(prof["id"])
