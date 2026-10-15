"""Funktionen vorschlagen (V01.0.380, plan plaene/funktionen-entdecken.md): the assistant points out a function that
is not on yet when it would help, and helps setting it up.

Off by default: admin chat.feature_tips (Funktionen → "Funktionen vorschlagen"), then for every profile the admin
did not block; a weekly note under "Von selbst" needs chat.feature_tips_push and the profile's pro_tips too.
Guests never get one.

The panel decides, never the model: which hint comes is fixed rules over what the panel knows itself
(features.reason, the Weiche's group, the profile's devices, accounts and counts), and nothing switches by itself.
A switch the profile may set itself goes on a card (hilfe.build_card, the same allowlist and checks as
"Einstellungen vorschlagen"); everything else is a guided setup: the guide's steps, a jump to the row where it is
set (_way), and "Prüfen" asks features.reason and the panel's own check (onboard.done) again. Something only the
admin can switch on: "Admin fragen" (a push to the admin profiles, once a day, only the function's name).

Kinds (plan 1-4): "wish" (asked for something whose function is off: intent.explain), "gap" (half set up),
"repeat" (done often by hand, counted per kind of question only, never the words), "new" (the admin released a
function this profile still sets up itself, its item under Los geht's in onboard.py; gone once that is done, once
"Prüfen" said it works, or NEW_DAYS after the release). Sparing: at most one hint per conversation and three a
week in the chat and as notes; "Nicht mehr zeigen" is for good; none after outside text, under the Notaus, at a
speaker, on Telegram or over MCP. The list under Ich → Überblick shows at most three and does not count as a hint.
"""
import json
import os
import re
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import notaus
import onboard
import profiles
from common import STATE, write_json
from core import assistant, browser_profile

FILE = os.path.join(STATE, "tipps.json")
WEEK = 7 * 86400
PER_WEEK = 3          # hints in the chat and as notes, per profile and week
MAX_LIST = 3          # entries under Ich → Überblick
ASK_GAP = 86400       # "Admin fragen": once a day per profile
KEEP_DAYS = 14        # the counts per kind of question
NEW_DAYS = 14         # a "new" hint ends this many days after the admin released the function, set up or not
MAX_CONVS = 40
TID = re.compile(r"[fg]:[a-z0-9_]{1,24}")
QUIET_ORIGINS = {"speaker", "telefon", "watch", "siri", "telegram", "mcp"}

_lock = threading.RLock()
# what tipps.json keeps per profile; "done": hints whose "Prüfen" said it works (they do not come again)
FIELDS = (("never", []), ("done", []), ("shown", []), ("convs", []), ("gaps", {}), ("ask", {}), ("count", {}))
router = APIRouter()


def push_on(uid, c=None):
    return features.allowed("tipps", uid, c) and features.allowed("tippspush", uid, c)


# ---------------------------------------------------------------- per profile: counts and what was shown
def _all():
    try:
        with open(FILE) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _st(uid):
    with _lock:
        st = _all().get(uid)
    st = st if isinstance(st, dict) else {}
    for k, v in FIELDS:
        if not isinstance(st.get(k), type(v)):
            st[k] = type(v)()
    return st


def _mut(uid, fn):
    with _lock:
        d = _all()
        st = d.get(uid) if isinstance(d.get(uid), dict) else {}
        for k, v in FIELDS:
            if not isinstance(st.get(k), type(v)):
                st[k] = type(v)()
        st.setdefault("since", int(time.time()))
        fn(st)
        d = {u: v for u, v in d.items() if u in set(profiles.user_ids()) or u == uid}
        d[uid] = st
        try:
            write_json(FILE, d)
        except OSError:
            pass
        return st


def forget(uid):
    with _lock:
        d = _all()
        if d.pop(uid, None) is not None:
            try:
                write_json(FILE, d)
            except OSError:
                pass


def record(uid, names, spoken, now=None):
    """Counts the kinds of this question (the Weiche's groups, spoken or typed) for "repeat"; never the words."""
    if not features.allowed("tipps", uid):
        return
    kinds = [n for n in names if n in ("websuche", "dokument", "erinnerung")][:3] + (["spoken"] if spoken else [])
    if not kinds:
        return
    day = time.strftime("%Y-%m-%d", time.localtime(now or time.time()))

    def put(st):
        c = st["count"]
        for d in sorted(c)[:-KEEP_DAYS]:
            c.pop(d, None)
        today = c.setdefault(day, {})
        for k in kinds:
            today[k] = min(9999, int(today.get(k, 0)) + 1)
    _mut(uid, put)


def _week_counts(st, now=None):
    now = now or time.time()
    days = {time.strftime("%Y-%m-%d", time.localtime(now - i * 86400)) for i in range(7)}
    out = {}
    for d, kinds in st["count"].items():
        if d in days and isinstance(kinds, dict):
            for k, n in kinds.items():
                out[k] = out.get(k, 0) + (n if isinstance(n, int) else 0)
    return out


# ---------------------------------------------------------------- one hint
def _name(key):
    f = features.BY_KEY[key]
    return [f.de, f.en]


def _how(key, uid, admin, c=None):
    """apply (one tap on a card), setup (guided), ask (only the admin can), admin (the admin switches it in Funktionen)."""
    import hilfe
    why = features.reason(key, uid, c)
    if why == "spark":
        return "admin" if admin else "ask"
    f = features.BY_KEY[key]
    if why == "profile" and key in hilfe.APPLY_PROFILE and f.pref:
        return "apply"
    return "setup"


def _tip(kind, tid, key, uid, admin, why, name=None, me=None, guide=None, c=None):
    f = features.BY_KEY.get(key) if key else None
    return {"id": tid, "kind": kind, "key": key or "", "name": name or (_name(key) if f else ["", ""]), "why": why,
            "me": me if me is not None else (f.me if f else ""), "guide": guide or (f.guide if f else ""),
            "how": _how(key, uid, admin, c) if f else "setup"}


def _quiet(uid, org, outside):
    return (org in QUIET_ORIGINS) or outside or notaus.refuse("aktion", uid)


def _may(st, tid, conv, now):
    if tid in st["never"]:
        return False
    if sum(1 for t in st["shown"] if isinstance(t, (int, float)) and now - t < WEEK) >= PER_WEEK:
        return False
    return not (conv and conv in st["convs"])


def _count_shown(uid, conv, now, tid):
    def put(st):
        st["shown"] = [t for t in st["shown"] if isinstance(t, (int, float)) and now - t < WEEK] + [int(now)]
        if conv:
            st["convs"] = (st["convs"] + [conv])[-MAX_CONVS:]
        if tid.startswith("g:"):
            st["gaps"][tid] = int(now)
    _mut(uid, put)


WISH_WHY = {"profile": ("Das kann ich, wenn du es einschaltest.", "I can do that once you switch it on."),
            "spark": ("Das kann ich, wenn der Admin es einschaltet.", "I can do that once the admin switches it on."),
            "mfa": ("Dafür braucht es zuerst den zweiten Anmeldeschritt.", "That needs the second sign-in step first.")}


def wish(uid, explain, conv="", org="panel", outside=False, admin=False, now=None):
    """Plan 1: the person asked for something whose function is off (intent.explain). The hint or None."""
    now = now or time.time()
    if not explain or not features.allowed("tipps", uid) or _quiet(uid, org, outside) or explain.get("why") not in WISH_WHY:
        return None
    key = explain.get("key")
    if key not in features.BY_KEY:
        return None
    tid = "f:" + key
    if not _may(_st(uid), tid, conv, now):
        return None
    w = WISH_WHY[explain["why"]]
    tip = _tip("wish", tid, key, uid, admin, list(w))
    _count_shown(uid, conv, now, tid)
    _event("wish")
    print(f"tipps: Hinweis wish {key} ({tip['how']})", flush=True)
    return tip


# ---------------------------------------------------------------- half set up, done often, new (plan 2-4)
def _my_devices(uid):
    try:
        return profiles.own_devices(uid)
    except Exception:
        return []


def _has_mail(uid):
    try:
        import mail
        return bool(mail.public(uid)["accounts"])
    except Exception:
        return False


def _has_calendar(uid):
    try:
        import calendars
        return bool(calendars.public(uid)["calendars"])
    except Exception:
        return False


def _has_speaker(uid):
    try:
        import esp32
        mine = {d["id"] for d in _my_devices(uid)}
        return any(v.get("device") in mine for v in esp32.clients().values())
    except Exception:
        return False


def _mfa_on(uid):
    try:
        import mfa
        return mfa.enabled(uid)
    except Exception:
        return False


def _passkeys(uid):
    try:
        import passkey
        return bool(passkey.listing(uid))
    except Exception:
        return True


def _voice(uid):
    try:
        import speakers
        return speakers.has_voice(uid)
    except Exception:
        return True


def _off(key, uid, c):
    """The function would help and is not on for this profile (but the Spark has it, or the admin can switch it)."""
    return features.reason(key, uid, c) in ("profile", "spark", "mfa")


# (id, function, condition(uid, c), reason de/en); a pseudo id without a function names its own Ich page
GAPS = (
    ("g:apppush", "iphonepush", lambda u, c: any(d["app"] for d in _my_devices(u)) and features.allowed("iphone", u, c)
     and _off("iphonepush", u, c), ("weil deine iPhone-App gekoppelt ist", "because your iPhone app is paired")),
    ("g:mailwichtig", "mailwichtig", lambda u, c: _has_mail(u) and features.allowed("mail", u, c) and _off("mailwichtig", u, c),
     ("weil dein Postfach verbunden ist", "because your mailbox is connected")),
    ("g:parcels", "parcels", lambda u, c: _has_mail(u) and features.allowed("mail", u, c) and _off("parcels", u, c),
     ("weil dein Postfach verbunden ist", "because your mailbox is connected")),
    ("g:briefing", "proactive", lambda u, c: _has_calendar(u) and _off("proactive", u, c),
     ("weil dein Kalender verbunden ist: Termine kommen dann von selbst", "because your calendar is connected: appointments then come by themselves")),
    ("g:mfa", "mfa", lambda u, c: (_has_mail(u) or _has_calendar(u)) and features.admin_on("mfa", c) and not _mfa_on(u),
     ("weil Mail oder Kalender verbunden sind: schützt dein Profil", "because mail or calendar is connected: protects your profile")),
    ("g:passkey", None, lambda u, c: _mfa_on(u) and not _passkeys(u),
     ("weil dein zweiter Anmeldeschritt an ist: Face ID oder Fingerabdruck statt Code", "because your second sign-in step is on: Face ID or fingerprint instead of the code")),
    ("g:speaker", "speaker", lambda u, c: _has_speaker(u) and features.allowed("speaker", u, c) and not _voice(u),
     ("weil du einen eigenen Lautsprecher hast: er erkennt dann deine Stimme", "because you have an own speaker: it then knows your voice")),
)
PSEUDO = {"g:passkey": (["Passkeys", "Passkeys"], "secbox", "mfa")}

# (id, kind counted, at least per week, function)
REPEATS = (
    ("websuche", 5, "lokal", ("weil du oft im Web suchst: erst das eigene Archiv und Wikipedia, schneller und im Haus",
                              "because you often search the web: own archive and Wikipedia first, faster and at home")),
    ("spoken", 10, "routing", ("weil du oft sprichst: weniger Fehlgriffe, etwas schneller", "because you talk a lot: fewer mistakes, a bit faster")),
    ("spoken", 10, "follow", ("weil du oft sprichst: „Und morgen?“ ohne „Hey Spark“", "because you talk a lot: \"And tomorrow?\" without \"Hey Spark\"")),
    ("dokument", 3, "docmeaning", ("weil du oft in deinen Dokumenten suchst: findet auch andere Worte",
                                  "because you often search your documents: finds other words too")),
    ("erinnerung", 3, "iphonepush", ("weil du oft Erinnerungen setzt: sie kommen dann aufs iPhone", "because you set reminders often: they then reach your iPhone")),
)


def candidates(uid, admin=False, c=None, now=None):
    """Plan 2-4: every hint that fits this profile now, best first (gaps, then repeats, then new)."""
    c = features.chat_cfg() if c is None else c
    now = now or time.time()
    st = _st(uid)
    out = []
    for tid, key, cond, why in GAPS:
        try:
            ok = cond(uid, c)
        except Exception:
            ok = False
        if ok and tid not in st["never"]:
            if key:
                out.append(_tip("gap", tid, key, uid, admin, list(why), c=c))
            else:
                name, me, guide = PSEUDO[tid]
                out.append(_tip("gap", tid, None, uid, admin, list(why), name=name, me=me, guide=guide, c=c))
    counts = _week_counts(st, now)
    for kind, least, key, why in REPEATS:
        tid = "f:" + key
        if counts.get(kind, 0) >= least and _off(key, uid, c) and tid not in st["never"] \
                and not any(x["id"] == tid or x["key"] == key for x in out):
            if key == "iphonepush" and not any(d["app"] for d in _my_devices(uid)):
                continue
            out.append(_tip("repeat", tid, key, uid, admin, list(why), c=c))
    try:
        seen = features._seen(c)
    except Exception:
        seen = {}
    since = st.get("since") or now
    for f in features.FEATURES:
        tid = "f:" + f.key
        # Newly released by the admin. Since Freigabe vereinfachen it works for this profile at once, so only a
        # function the profile still sets up itself (its item under Los geht's, onboard.py) is a hint, and only
        # until that is done, "Prüfen" said it works, or NEW_DAYS have passed.
        own = onboard.own_setup(f.key, c) if not f.parent else None
        if own and since < seen.get(f.key, 0) and now - seen[f.key] < NEW_DAYS * 86400 \
                and features.reason(f.key, uid, c) is None and tid not in st["never"] and tid not in st["done"] \
                and not any(x["key"] == f.key for x in out) and not onboard.done(own[0], uid):
            out.append(_tip("new", tid, f.key, uid, admin, ["neu freigegeben, noch einzurichten",
                                                             "newly released, still to set up"], me=own[1], c=c))
    return out


def listing(uid, admin=False, c=None):
    """Ich → Überblick "Für dich vorgeschlagen": at most three, each with its reason."""
    if not features.allowed("tipps", uid, c):
        return []
    return candidates(uid, admin, c)[:MAX_LIST]


def weekly_text(uid, now=None):
    """Plan 7: one note a week under "Von selbst" (proactive.check_tips), or "" (counts as a hint)."""
    now = now or time.time()
    if not push_on(uid) or notaus.refuse("aktion", uid):
        return "", None
    st = _st(uid)
    if now - st.get("push", 0) < WEEK:
        return "", None
    items = [x for x in candidates(uid) if _may(st, x["id"], "", now)]
    if not items:
        return "", None
    x = items[0]

    def put(s):
        s["push"] = int(now)
    _mut(uid, put)
    _count_shown(uid, "", now, x["id"])
    _event("push")
    return (f"Tipp: {x['name'][0]}, {x['why'][0]}. Unter Ich → Überblick kannst du es einrichten "
            "oder „Nicht mehr zeigen“ wählen."), x


# ---------------------------------------------------------------- setting up (plan 5)
def steps(guide_id, lang="de", admin=False):
    """The guide's own setup steps (guides.js), the admin's steps left out for a profile."""
    import hilfe
    li = 0 if lang == "de" else 1
    g = next((x for x in hilfe.guides() if x["id"] == guide_id), None)
    if not g:
        return []
    return [s for s in g["sec"].get("setup", ([], []))[li] if s and (admin or not s.startswith("Admin"))][:8]


WAY_ME = re.compile(r"(?<![\w-])(Ich|Me) → ")


def _way(x, todo, lang="de"):
    """Where "Seite öffnen" jumps (way.js wayGo): the first way into Ich in the guide's own steps (the row or part
    the person fills in, „Ich → Kalender → „Kalender hinzufügen““), else the function's row on its Ich page, else
    the page."""
    for s in todo:
        m = WAY_ME.search(s)
        if m:
            return s[m.start():][:200]
    import hilfe
    f = features.BY_KEY.get(x["key"]) if x["key"] else None
    if f and f.me == x["me"]:
        return features.me_way(f.key, lang)
    return hilfe.page_name("me/" + x["me"], lang) if x["me"] else ""


def _find(uid, tid, admin, c=None):
    """A hint this profile may act on: one of its candidates, or any function by its own key (the chat's card)."""
    if not TID.fullmatch(tid or ""):
        raise HTTPException(404, "unknown hint")
    for x in candidates(uid, admin, c):
        if x["id"] == tid:
            return x
    key = tid[2:]
    if tid.startswith("f:") and key in features.BY_KEY:
        return _tip("wish", tid, key, uid, admin, ["", ""], c=c)
    raise HTTPException(404, "unknown hint")


def _admins():
    """The profiles that look after the Spark (coadmin roles)."""
    try:
        import coadmin
        return [u["id"] for u in coadmin.listing()["users"]]
    except Exception:
        return []


def _event(what):
    try:
        import live
        live.event("Funktionen vorschlagen", {"wish": "Hinweis im Gespräch", "push": "Hinweis von selbst",
                                              "apply": "übernommen", "never": "nicht mehr zeigen", "ask": "Admin gefragt",
                                              "setup": "Einrichten geöffnet", "ok": "eingerichtet"}.get(what, what))
    except Exception:
        pass


@router.get("/api/profile/tipps", dependencies=[Depends(assistant)])
def api_list(request: Request, prof=Depends(browser_profile)):
    import hilfe
    admin = hilfe.admin_here(request) != "profile"
    return {"on": features.allowed("tipps", prof["id"]), "items": listing(prof["id"], admin)}


@router.post("/api/profile/tipps/{tid}", dependencies=[Depends(assistant)])
async def api_do(tid: str, request: Request, prof=Depends(browser_profile)):
    """{"do": "setup" | "check" | "never" | "ask"}: the person's tap on a hint."""
    import hilfe
    uid = prof["id"]
    guard.limit(request, "tipps", uid)
    body = await request.json()
    do = body.get("do") if isinstance(body, dict) else None
    lang = "en" if isinstance(body, dict) and body.get("lang") == "en" else "de"
    if do not in ("setup", "check", "never", "ask"):
        raise HTTPException(400, "do: setup, check, never or ask")
    if not features.allowed("tipps", uid):
        raise HTTPException(403, "Funktionen vorschlagen ist aus")
    admin = hilfe.admin_here(request) != "profile"
    x = _find(uid, tid, admin)
    if do == "never":
        _mut(uid, lambda st: st["never"].append(tid) if tid not in st["never"] else None)
        _event("never")
        print(f"tipps: nicht mehr zeigen {tid}", flush=True)
        return {"state": "never"}
    if do == "check":
        key = x["key"]
        if not key:   # a pseudo hint: asked again from the facts
            ok = not any(t["id"] == tid for t in candidates(uid, admin))
            return {"ok": ok, "why": "" if ok else ("Noch nicht eingerichtet." if lang == "de" else "Not set up yet.")}
        why = features.reason(key, uid)
        own = onboard.own_setup(key)
        if why is None and own and not onboard.done(own[0], uid):
            print(f"tipps: noch nicht eingerichtet {key}", flush=True)
            return {"ok": False, "why": "Noch nicht eingerichtet." if lang == "de" else "Not set up yet."}
        if why is not None:
            print(f"tipps: noch nicht eingerichtet {key} ({why})", flush=True)
            return {"ok": False, "why": features.WHY[why][0 if lang == "de" else 1]}
        _mut(uid, lambda st: st["done"].append(tid) if tid not in st["done"] else None)
        _event("ok")
        print(f"tipps: eingerichtet {key}", flush=True)
        return {"ok": True, "why": ""}
    if do == "ask":
        if x["how"] != "ask":
            raise HTTPException(409, "Das kannst du selbst einrichten.")
        if notaus.refuse("aktion", uid):
            raise HTTPException(423, f"Notaus Stufe {notaus.level()}: Änderungen sind angehalten")
        st = _st(uid)
        if time.time() - st["ask"].get("_last", 0) < ASK_GAP:
            raise HTTPException(429, "Heute hast du den Admin schon gefragt.")
        _mut(uid, lambda s: s["ask"].update({"_last": int(time.time()), tid: int(time.time())}))
        who = (profiles.by_id(uid) or {}).get("name", "")
        import push
        n = 0
        for a in _admins():
            if a != uid:
                try:
                    n += await push.send(a, "Funktion gewünscht", f"{who} möchte „{x['name'][0]}“ benutzen. "
                                         "Einschalten unter Funktionen.", tag="admin", private=False,
                                         why="Funktion gewünscht")
                except Exception as e:
                    print("tipps: Admin fragen:", type(e).__name__, flush=True)
        guard.log("tipp_ask", uid=uid, detail=x["key"][:40])
        _event("ask")
        print(f"tipps: Admin gefragt {x['key']} ({n} Geräte)", flush=True)
        return {"state": "asked", "reached": n}
    # setup: the steps, the way to the setting, and for a plain own switch the card to apply it with one tap
    todo = steps(x["guide"], lang, x["how"] == "admin")
    out = {"name": x["name"], "me": x["me"], "how": x["how"], "steps": todo, "card": None, "way": _way(x, todo, lang),
           "admin_way": ("Funktionen → " if lang == "de" else "Features → ") + x["name"][0 if lang == "de" else 1]
           if x["how"] == "admin" else ""}
    if x["how"] == "apply" and not notaus.refuse("aktion", uid):
        card = hilfe.build_card(uid, [x["key"]], True, False, lang)
        if card and card.get("id"):
            card["src"] = "tipp"
            out["card"] = hilfe.public(card)
    _event("setup")
    print(f"tipps: Einrichten {tid} ({x['how']})", flush=True)
    return out
