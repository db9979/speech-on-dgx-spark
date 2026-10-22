"""Funktionen → Weiche → unklar: unclear questions, anonymized (plan unklare-fragen, Dominik 2026-10-22).

A question no rule of the Weiche recognized („unklar“) is kept for the admin to tune the rules with: only its text
after the fixed anonymizer, never a profile, a device or a time of day (only the day, to let it go after KEEP_DAYS).
The same sentence twice is one row with a count; beside it the group whose tool the model then took (weiche.learn).

Anonymizing is fixed rules only, never a model (Richtlinie 2.3, 2.7):
  1. a sentence with the smart-home code word („[Codewort]“, homeassistant.redact) is never kept;
  2. the anonymizer of „Probleme melden“ (meldung.Anon with meldung.known(): names of profiles, devices and accounts,
     mail addresses, links, host names, IPs, MACs, phone numbers, places, long codes, every plain secret);
  3. the names in the asking profile's own address book, a name after „Herr/Frau/Dr.“ → [PERSON];
  4. every digit that is left → [ZAHL];
  5. the leak check of „Probleme melden“ (meldung.leaks) once more on the result: finds it anything, the question is
     dropped and only counted („verworfen“).

Who: the admin switch chat.route_unklar (off), for every profile it releases unless the admin blocked it, and the
profile's preference unklar_anon (on, Ich → Gespräch → Datenschutz). Never guests or a voice taken for a guest.
Seen and deleted only on Funktionen → Weiche (admin and Mit-Admin, not the Verwalter). Kept sealed (vault) in
STATE/weiche-unklar.json, at most MAX_ROWS sentences, KEEP_DAYS days.
"""
import hashlib
import json
import os
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import vault
from common import STATE, write_json
from core import auth

router = APIRouter()
KEEP_DAYS = 7
MAX_ROWS = 100
MAX_Q = 200            # longer questions are cut, like a test sentence of the Weiche (weiche.MAX_Q)
KNOWN_S = 600          # meldung.known() is read anew after this many seconds (profiles, devices, accounts, secrets)
CODEWORD = "[Codewort]"
# a placeholder of the anonymizer: shown as it is, never offered as a word of a group (weiche.suggest)
HOLDER = re.compile(r"\[(?:PERSON|GERÄT|KONTO|MAIL|URL|HOST|IP|IP-LAN|MAC|TELEFON|ORT|GEHEIM|INHALT|ID|ZAHL)\]")
_NUMBERED = re.compile(r"\[(PERSON|GERÄT|KONTO)-\d+\]")
_TITLE = re.compile(r"(?<![\w-])(Herrn?|Frau|Dr\.|Prof\.|Mr\.|Mrs\.|Ms\.)\s+[A-ZÄÖÜ][\w'-]{1,40}(?:\s+[A-ZÄÖÜ][\w'-]{1,40})?")
_DIGITS = re.compile(r"\d+(?:[.,:]\d+)*")
_ID = re.compile(r"[0-9a-f]{10}")
_lock = threading.Lock()
_known = {"t": 0.0, "k": None, "anon": None}
_contacts = {}     # uid -> (cards list identity, compiled pattern or None)


def on(ch=None):
    return features.admin_on("weicheunklar", ch)


def _now_known():
    """meldung.known() and one Anon built on it, read anew every KNOWN_S seconds (the name pattern is large)."""
    import meldung
    with _lock:
        if _known["k"] is None or time.monotonic() - _known["t"] > KNOWN_S:
            k = meldung.known()
            _known.update(t=time.monotonic(), k=k, anon=meldung.Anon(k))
        return _known["k"], _known["anon"]


def _contact_names(uid):
    """The asking profile's own address book as one pattern of names (first, last and whole names), or None."""
    try:
        import contacts
        cards = contacts.cards(uid)
    except Exception:
        return None
    hit = _contacts.get(uid)
    if hit and hit[0] is cards:
        return hit[1]
    names = set()
    for c in cards[:5000]:
        whole = str(c.get("name") or "").strip()
        for part in [whole] + whole.split():
            part = part.strip(",.;:()\"'")
            if 3 <= len(part) <= 60:
                names.add(part.lower())
    pat = re.compile(r"(?i)(?<![\w-])(" + "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)[:6000])
                     + r")(?![\w-])") if names else None
    _contacts[uid] = (cards, pat)
    return pat


def anon(text, uid=None):
    """The question with every personal part replaced by a placeholder, or None when it must not be kept (code word,
    empty, or the leak check still finds something)."""
    import meldung
    text = " ".join(str(text or "").split())[:MAX_Q]
    if not text or CODEWORD.lower() in text.lower():
        return None
    k, a = _now_known()
    with _lock:   # one Anon for all: its numbering is cleared for each question
        a.n, a.map = {}, {}
        s = a.text(text)
    s = s.replace("​", "").replace("'''", "")
    s = _NUMBERED.sub(lambda m: f"[{m.group(1)}]", s)
    s = _TITLE.sub(lambda m: m.group(1) + " [PERSON]", s)
    pat = _contact_names(uid) if uid else None
    if pat:
        s = pat.sub("[PERSON]", s)
    s = _DIGITS.sub("[ZAHL]", s)
    s = " ".join(s.split())
    if not HOLDER.sub("", s).strip(" ?!.,;:-") or meldung.leaks(s, k) or (pat and pat.search(HOLDER.sub(" ", s))):
        return None
    return s


def _id(q):
    return hashlib.sha256(q.lower().encode()).hexdigest()[:10]


def _path():
    return os.path.join(STATE, "weiche-unklar.json")


def _read():
    try:
        with open(_path()) as f:
            raw = f.read()
        d = json.loads(vault.open_(raw.strip()) or "{}") if raw.strip().startswith(vault.PREFIX) else json.loads(raw)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(d):
    os.makedirs(STATE, exist_ok=True)
    plain = json.dumps(d, ensure_ascii=False)
    sealed = vault.seal(plain)
    if sealed == plain:     # no key on this Spark: written plain, like the other statistics
        write_json(_path(), d)
        return
    tmp = _path() + ".tmp"
    with open(tmp, "w") as f:
        f.write(sealed)
    os.chmod(tmp, 0o600)
    os.replace(tmp, _path())


def _day(now):
    return time.strftime("%Y-%m-%d", time.localtime(now))


def _clean(d, now):
    """Rows of the last KEEP_DAYS days, at most MAX_ROWS (the oldest go first); drop counts only of those days."""
    oldest = _day(now - KEEP_DAYS * 86400)
    rows = [r for r in d.get("rows", []) if isinstance(r, dict) and isinstance(r.get("q"), str) and str(r.get("day", "")) > oldest]
    rows.sort(key=lambda r: (r.get("day", ""), r.get("n", 0)), reverse=True)
    dropped = {k: int(v) for k, v in (d.get("dropped") or {}).items() if isinstance(k, str) and k > oldest
               and isinstance(v, int)}
    return {"rows": rows[:MAX_ROWS], "dropped": dropped}


def wanted(who, guest, route, ch=None):
    """This turn may keep its question: an unclear question of a profile (never a guest) with everything released."""
    return bool(who and not guest and route is not None and not route.names
                and features.allowed("weicheunklar", who["id"], ch))


def keep(route, text, uid, now=None):
    """Called once per unclear turn, in its own thread (chat_turn): anonymize and keep, or count as dropped."""
    now = time.time() if now is None else now
    try:
        q = anon(text, uid)
    except Exception as e:
        print("weiche: unklare Frage nicht anonymisiert", type(e).__name__, flush=True)
        q = None
    with _lock:
        d = _clean(_read(), now)
        if q is None:
            day = _day(now)
            d["dropped"][day] = d["dropped"].get(day, 0) + 1
        else:
            rid = _id(q)
            row = next((r for r in d["rows"] if r.get("id") == rid), None)
            if row is None:
                row = {"id": rid, "q": q, "n": 0, "took": {}}
                d["rows"].insert(0, row)
            row["n"] = int(row.get("n", 0)) + 1
            row["day"] = _day(now)
            took = getattr(route, "unklar_took", None)
            if took:
                row["took"][took] = int(row["took"].get(took, 0)) + 1
            route.unklar_id = rid
        try:
            _write(_clean(d, now))
        except OSError as e:
            print("weiche: unklare Fragen nicht gespeichert", type(e).__name__, flush=True)
            return None
    print("weiche: unklare Frage", "verworfen (Prüfung)" if q is None else "anonym gemerkt", flush=True)
    return q


def start(route, text, uid):
    """chat_turn: keep in the background, the answer never waits for it."""
    if not isinstance(text, str) or not text.strip():
        return
    threading.Thread(target=keep, args=(route, text, uid), daemon=True, name="weiche-unklar").start()


def took(route, group):
    """weiche.learn: the model ran a tool of this group first; added to the row of this turn (or remembered on the
    turn until keep() has written it)."""
    if route is None or not group:
        return
    with _lock:
        rid = getattr(route, "unklar_id", None)
        if not rid:
            route.unklar_took = group
            return
        d = _read()
        for r in d.get("rows", []):
            if r.get("id") == rid:
                r.setdefault("took", {})[group] = int(r.get("took", {}).get(group, 0)) + 1
                try:
                    _write(d)
                except OSError:
                    pass
                return


def view(now=None):
    """For the Weiche page: the rows (newest first) and how many were dropped in the last days."""
    import intent
    now = time.time() if now is None else now
    with _lock:
        d = _clean(_read(), now)
    rows = []
    for r in d["rows"]:
        took = sorted(((g, n) for g, n in (r.get("took") or {}).items() if g in intent.GROUPS), key=lambda x: -x[1])
        rows.append({"id": r["id"], "q": r["q"], "n": int(r.get("n", 0)), "day": r.get("day", ""),
                     "took": took[0][0] if took else ""})
    return {"on": on(), "rows": rows, "dropped": sum(d["dropped"].values()), "keep_days": KEEP_DAYS, "max": MAX_ROWS}


def count_today(now=None):
    """Live: how many sentences are kept (numbers only)."""
    try:
        return len(_clean(_read(), time.time() if now is None else now)["rows"])
    except Exception:
        return 0


def remove(rid=None):
    """One row (rid) or all. Returns how many went."""
    with _lock:
        d = _read()
        rows = d.get("rows", []) if isinstance(d.get("rows"), list) else []
        left = [r for r in rows if rid is not None and isinstance(r, dict) and r.get("id") != rid]
        gone = len(rows) - len(left)
        if rid is None:
            d = {"rows": [], "dropped": {}}
        else:
            d["rows"] = left
        if os.path.exists(_path()):
            _write(d)
    return gone


@router.delete("/api/admin/weiche/unklar", dependencies=[Depends(auth)])
def delete_all(request: Request):
    guard.limit(request, "route", None, True)
    n = remove()
    print("weiche: unklare Fragen gelöscht", n, flush=True)
    guard.log("weiche_unklar_weg", detail=f"alle, {n}")
    return {"ok": True, "gone": n}


@router.delete("/api/admin/weiche/unklar/{rid}", dependencies=[Depends(auth)])
def delete_one(rid: str, request: Request):
    guard.limit(request, "route", None, True)
    if not _ID.fullmatch(rid):
        raise HTTPException(400, "id")
    n = remove(rid)
    print("weiche: unklare Frage gelöscht", n, flush=True)
    guard.log("weiche_unklar_weg", detail=f"eine, {n}")
    return {"ok": True, "gone": n}
