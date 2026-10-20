"""Alles Offene im Assistenten (plan assistent-zentrale/plan.md, Dominik 2026-10-20 „ok“ = 1a-8a, stage 1): what needs
the person becomes one Vorgang in one place per profile. The card in the conversation, the page Offen (Braucht dich,
Später, Erledigt) and a note on a device carry the same number; done on one device is done on every one.

Fixed rules, the panel decides: only modules of the panel make a Vorgang (put), never the model; a card is data, its
buttons are names from AKTIONEN, each checked here (owner, kind, right, rev, Notaus) before the module's own function
runs. Titles and lines are the panel's words; a sender or subject from a mail is outside text, shown as text only.

    ARTEN       the kinds: name de/en, symbol, buttons, urgent ("dringend", the one list push reads), from mail
    AKTIONEN    every button: name de/en, stage ("direkt": at once with Rückgängig, "seite": opens the page where the
                person goes on), the function behind it
    put()       makes or updates one Vorgang by its key (Sachschlüssel: "fuerdich:<id>", "erinnerung:<id>"); the same
                key never makes a second one and never rings twice
    seen()      a device showed it (stops a follow-up push, thread „Benachrichtigung nur aufs aktive Gerät“)
    done()      the source says it is done elsewhere (Für dich marked on the mail page …)
    due()       every minute: Später is over → open again, once more into the conversation and onto a device

    GET  /api/profile/vorgaenge?seit=<rev>   the changed ones (all without seit), with "rev" and the counts
    DELETE /api/profile/vorgaenge?nur=erledigt  the done ones (or all) of this profile away
    GET  /api/profile/vorgaenge/stream       {"type": "vorgang", "rev": n, "neu": bool, "weg": bool}: never text
    POST /api/profile/vorgaenge/act          {"id", "act", "rev", "wann"?}: one button

Kept in users/<id>/vorgaenge.json: the open ones, the ones for later and the done ones of the last ERLEDIGT_TAGE days.
Off until the admin switches chat.vorgaenge on (needs chat.reminders); then for every profile the admin did not
block; guests never. A card goes into today's main conversation (verlauf.main_today) as an assistant message with
"vg", so every device shows it where the conversation is, and an old conversation shows today's state.
"""
import datetime
import os
import re
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import notaus
import profiles
import sse
from common import DayCounter
from core import assistant, json_body, own_profile

router = APIRouter()

# the kinds (stage 1: Für dich and reminders; plan stages 2-4 add Kalender, Mail, Nachrichten, Geteilt, Dienste)
ARTEN = {
    "fuerdich": {"de": "Für dich", "en": "For you", "sym": "mail", "mail": True, "dringend": False,
                 "acts": ("fd_remind", "fd_event", "fd_reply", "fd_cancel", "fd_more", "erledigt", "ausblenden")},
    "erinnerung": {"de": "Erinnerung", "en": "Reminder", "sym": "bell", "mail": False, "dringend": True,
                   "acts": ("erledigt",)},
}
# every button there is; "direkt" runs here at once (Rückgängig with "zurueck"), "seite" only opens the place where
# the person goes on (the mail page's preview sheet sends, the Kalender's „Eintragen“ saves), nothing runs here
AKTIONEN = {
    "erledigt": {"de": "Erledigt", "en": "Done", "stufe": "direkt"},
    "ausblenden": {"de": "Nicht wichtig", "en": "Not important", "stufe": "direkt"},
    "spaeter": {"de": "Später", "en": "Later", "stufe": "direkt"},
    "zurueck": {"de": "Zurückholen", "en": "Bring back", "stufe": "direkt"},
    "fd_remind": {"de": "Erinnern", "en": "Remind me", "stufe": "direkt"},
    "fd_more": {"de": "Mehr davon", "en": "More of this", "stufe": "direkt"},
    "fd_event": {"de": "Eintragen …", "en": "Add to calendar …", "stufe": "seite"},
    "fd_reply": {"de": "Antwort entwerfen …", "en": "Draft a reply …", "stufe": "seite"},
    "fd_cancel": {"de": "Kündigung entwerfen …", "en": "Draft a cancellation …", "stufe": "seite"},
}
# „Später“: the four choices of the card (plan 4a), local time of the profile; "ohne" stays in Offen only
SPAETER = {"abend": ("Heute Abend", "This evening"), "morgen": ("Morgen früh", "Tomorrow morning"),
           "woche": ("Nächste Woche", "Next week"), "ohne": ("Ohne Zeit", "No time")}
ABEND, MORGEN = 18, 8
ZUSTAENDE = ("offen", "gesehen", "spaeter", "erledigt", "weg")
ERLEDIGT_TAGE = 7               # done and gone ones stay this long under „Erledigt“ (with „Zurückholen“)
ALT_TAGE = 30                   # an open one without a deadline goes after this ("weg")
ERINNERUNG_STUNDEN = 12         # a reminder that rang and was not pressed is gone after this
MAX_ITEMS = 300
# what a button that opens a page needs (Für dich: the calendar line, the mail's number, folder, sender, subject);
# a sender and a subject are outside text, shown and handed on as text only
DATEN = ("event", "ref", "folder", "fd", "addr", "subject")
MAX_TEXT = 160
ID = re.compile(r"v[0-9a-f]{10}")
KEY = re.compile(r"[a-z]{2,12}:[\w.:@-]{1,120}")

_lock = threading.Lock()
_day = DayCounter()             # per day: made, done, later, back (Zustand → Live, numbers only)
_hub = sse.Hub(20, 6, 25)       # open pages per profile get "vorgang" events (only numbers)
streams = _hub.count


# ---------------------------------------------------------------- the file
def _file(uid):
    return profiles._path(uid, "vorgaenge.json")


def _load(uid):
    import json
    try:
        with open(_file(uid)) as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    items = [x for x in (d.get("items") or []) if isinstance(x, dict) and ID.fullmatch(str(x.get("id", "")))
             and x.get("art") in ARTEN and x.get("zustand") in ZUSTAENDE]
    return {"items": items, "rev": int(d.get("rev") or 0)}


def _save(uid, d):
    profiles._write(_file(uid), {"items": d["items"][-MAX_ITEMS:], "rev": d["rev"]})


def _mut(uid, fn):
    """fn(d) changes the profile's Vorgänge under the lock; every changed item gets the next rev, items taken out
    count one more. Returns fn's result. The event says "weg" when some went: the pages then load all anew."""
    with _lock:
        d = _load(uid)
        before = {x["id"]: dict(x) for x in d["items"]}
        res = fn(d)
        changed = [x for x in d["items"] if before.get(x["id"]) != x]
        gone = len(set(before) - {x["id"] for x in d["items"]})
        for x in changed:
            d["rev"] += 1
            x["rev"] = d["rev"]
        d["rev"] += 1 if gone else 0
        if changed or gone:
            _save(uid, d)
    if changed or gone:
        _hub.send(uid, {"type": "vorgang", "rev": d["rev"], "neu": any(x["id"] not in before for x in changed),
                        "weg": bool(gone)})
    return res


def count(uid):
    """Kept Vorgänge (features.OWN, Daten löschen): a number, never contents."""
    return len(_load(uid)["items"])


def forget(uid):
    try:
        os.remove(_file(uid))
    except OSError:
        pass


features.OWN["vorgaenge"] = (count, forget)
profiles.REMINDER_HOOKS.append(lambda uid, item: from_reminder(uid, item))


def _clean(v, n=MAX_TEXT):
    return re.sub(r"[\x00-\x1f]+", " ", str(v or "")).strip()[:n]


# ---------------------------------------------------------------- making and closing
def put(uid, art, key, titel, zeile="", felder=(), frist="", daten=None, say=False, now=None):
    """Makes the Vorgang of key (or updates the words of the one there is). Returns (item, new) or (None, False) when
    the function is off for this profile. say: a new one also goes as a card into today's main conversation."""
    if not features.allowed("vorgaenge", uid) or art not in ARTEN or not KEY.fullmatch(str(key)):
        return None, False
    now = now or time.time()
    words = {"titel": _clean(titel), "zeile": _clean(zeile),
             "felder": [[_clean(a, 30), _clean(b)] for a, b in list(felder)[:6]], "frist": _clean(frist, 10),
             "daten": {k: _clean(v, 300) for k, v in (daten or {}).items() if k in DATEN}}

    def fn(d):
        x = next((y for y in d["items"] if y["key"] == key), None)
        if x is not None:
            x.update(words)
            return x, False
        x = dict(words, id="v" + secrets.token_hex(5), key=key, art=art, zustand="offen", t=int(now), ge=int(now),
                 zugestellt=[])
        d["items"].append(x)
        return x, True
    x, new = _mut(uid, fn)
    if new:
        _day.bump("neu")
        print(f"vorgang: neu {art} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
        if say:
            card_message(uid, x)
    return x, new


def card_message(uid, x):
    """The card as an assistant message of today's main conversation ("vg" is its number). The sentence is the
    panel's; a Vorgang from mail is marked "mail" like every answer made from mail."""
    import chat
    import verlauf
    local = datetime.datetime.now(chat.user_zone(profiles.effective(uid).get("tz", "")))
    cid, title = verlauf.main_today(uid, local)
    text = x["titel"] + (". " + x["zeile"] if x.get("zeile") else "")
    msg = {"role": "assistant", "content": text, "vg": x["id"], **({"mail": True} if ARTEN[x["art"]]["mail"] else {})}
    profiles.append_convo(uid, cid, title, [msg])


def say(uid, vid):
    """The card of one Vorgang into today's main conversation (Von selbst said it)."""
    x = next((y for y in _load(uid)["items"] if y["id"] == vid), None)
    if x:
        card_message(uid, x)
    return bool(x)


def _set(x, zustand, wie="", wo="", now=None):
    x["zustand"], x["ge"] = zustand, int(now or time.time())
    if wie:
        x["wie"] = wie
    else:
        x.pop("wie", None)
    if wo:
        x["wo"] = wo
    if zustand != "spaeter":
        x.pop("spaeter_bis", None)


def done(uid, key, wie="erledigt", wo=""):
    """The source says the thing is done (or not wanted) somewhere else; nothing when there is no such Vorgang."""
    if not os.path.exists(_file(uid)):
        return False

    def fn(d):
        x = next((y for y in d["items"] if y["key"] == key and y["zustand"] not in ("erledigt", "weg")), None)
        if x:
            _set(x, "erledigt" if wie == "erledigt" else "weg", wie, wo)
        return bool(x)
    hit = _mut(uid, fn)
    if hit:
        print(f"vorgang: erledigt anderswo {key.split(':')[0]} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return hit


def reopen(uid, key):
    """The source takes back a done mark (Für dich: „Markierungen vergessen“ or „Zurückholen“)."""
    if not os.path.exists(_file(uid)):
        return False

    def fn(d):
        x = next((y for y in d["items"] if y["key"] == key and y["zustand"] in ("erledigt", "weg")), None)
        if x:
            _set(x, "offen")
        return bool(x)
    hit = _mut(uid, fn)
    if hit:
        print(f"vorgang: wieder offen von der quelle {key.split(':')[0]} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return hit


def seen(uid, vid, weg=""):
    """A device showed it (open → gesehen); the other devices stop asking for it."""
    def fn(d):
        x = next((y for y in d["items"] if y["id"] == vid and y["zustand"] == "offen"), None)
        if x:
            x["zustand"] = "gesehen"
            x["seen"] = {"weg": _clean(weg, 10), "t": int(time.time())}
        return bool(x)
    return _mut(uid, fn)


def later_at(wann, local):
    """When „Später“ is over (epoch seconds) or 0 for "ohne". local: aware datetime in the profile's zone."""
    if wann == "ohne":
        return 0
    if wann == "abend":
        at = local.replace(hour=ABEND, minute=0, second=0, microsecond=0)
        if at <= local + datetime.timedelta(minutes=30):    # already evening: in three hours
            return int((local + datetime.timedelta(hours=3)).timestamp())
        return int(at.timestamp())
    days = 1 if wann == "morgen" else 7 - local.weekday() if local.weekday() < 6 else 1
    day = local.date() + datetime.timedelta(days=days if wann == "woche" else 1)
    return int(datetime.datetime.combine(day, datetime.time(MORGEN), local.tzinfo).timestamp())


# ---------------------------------------------------------------- what the pages and apps see
def group_of(x):
    return {"offen": "braucht", "gesehen": "braucht", "spaeter": "spaeter"}.get(x["zustand"], "erledigt")


def public(uid, x):
    a = ARTEN[x["art"]]
    ok = _allowed_acts(uid, x)
    acts = [k for k in a["acts"] + ("spaeter", "zurueck") if k in ok]
    return {"id": x["id"], "art": x["art"], "art_de": a["de"], "art_en": a["en"], "sym": a["sym"],
            "dringend": a["dringend"], "mail": a["mail"], "titel": x["titel"], "zeile": x.get("zeile", ""),
            "felder": x.get("felder", []), "frist": x.get("frist", ""), "zustand": x["zustand"], "gruppe": group_of(x),
            "spaeter_bis": x.get("spaeter_bis", 0), "t": x["t"], "ge": x["ge"], "wie": x.get("wie", ""),
            "wo": x.get("wo", ""), "rev": x.get("rev", 0), "daten": x.get("daten", {}),
            "acts": [{"k": k, "de": AKTIONEN[k]["de"], "en": AKTIONEN[k]["en"], "stufe": AKTIONEN[k]["stufe"]} for k in acts],
            "zugestellt": x.get("zugestellt", [])}


def counts(items):
    out = {"braucht": 0, "spaeter": 0, "erledigt": 0}
    for x in items:
        out[group_of(x)] += 1
    return out


def view(uid, seit=0):
    d = _load(uid)
    return {"rev": d["rev"], "items": [public(uid, x) for x in d["items"] if x.get("rev", 0) > seit],
            "counts": counts(d["items"]), "spaeter": {k: list(v) for k, v in SPAETER.items()}}


def _allowed_acts(uid, x):
    """The buttons of this Vorgang by fixed rules: the kind's list, the source's own rules, the state."""
    if x["zustand"] in ("erledigt", "weg"):
        return {"zurueck"}
    out = {"erledigt", "spaeter"} | ({"zurueck"} if x["zustand"] == "spaeter" else set())
    if x["art"] == "fuerdich":
        out.add("ausblenden")
        import fuerdich
        src = fuerdich.find(uid, x["key"].split(":", 1)[1])
        for k in (fuerdich.acts(uid, src) if src else []):
            out.add("fd_" + k)
    return out


# ---------------------------------------------------------------- the buttons
WO = {"web": "Rechner", "phone": "Handy", "app": "iPhone", "desk": "Begleiter", "tg": "Telegram"}


def act(uid, vid, name, rev=None, wann="", wo="web", now=None):
    """Runs one button. Returns {"item", "rev", ...}; raises HTTPException with a fixed sentence when it may not."""
    if name not in AKTIONEN:
        raise _refuse("aktion", 400, "Diesen Knopf gibt es nicht.")
    if notaus.refuse("aktion", uid):
        raise _refuse("notaus", 503, "Notaus: gerade wird nichts geändert.")
    d = _load(uid)
    x = next((y for y in d["items"] if y["id"] == vid), None)
    if x is None:
        raise _refuse("fehlt", 404, "Diesen Vorgang gibt es nicht mehr.")
    if rev is not None and int(rev) != x.get("rev", 0):
        _bump_refused()
        print(f"vorgang: knopf abgelehnt grund=rev {x['art']} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
        raise HTTPException(409, {"text": "Das hat sich gerade auf einem anderen Gerät geändert.",
                                  "item": public(uid, x), "rev": d["rev"]})
    if name not in _allowed_acts(uid, x) or name not in ARTEN[x["art"]]["acts"] + ("spaeter", "zurueck"):
        raise _refuse("nicht_erlaubt", 403, "Für diesen Vorgang gibt es diesen Knopf nicht.")
    if name == "spaeter" and wann not in SPAETER:
        raise _refuse("wann", 400, "Wann soll er wiederkommen?")
    now = now or time.time()
    where = WO.get(wo, "Rechner")
    extra = (_source_act(uid, x, name) or {}) if x["art"] == "fuerdich" and name != "spaeter" else {}
    if AKTIONEN[name]["stufe"] == "seite":
        print(f"vorgang: knopf {name} seite {x['art']} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
        return dict(extra, item=public(uid, x), rev=d["rev"])

    def fn(d2):
        y = next((z for z in d2["items"] if z["id"] == vid), None)
        if y is None:
            return None
        if name in ("erledigt", "fd_remind", "fd_more"):
            _set(y, "erledigt", name, where, now)
        elif name == "ausblenden":
            _set(y, "weg", name, where, now)
        elif name == "zurueck":
            _set(y, "offen", "", where, now)
        elif name == "spaeter":
            import chat
            local = datetime.datetime.fromtimestamp(now, chat.user_zone(profiles.effective(uid).get("tz", "")))
            _set(y, "spaeter", "", where, now)
            y["spaeter_bis"] = later_at(wann, local)
        return y
    y = _mut(uid, fn)
    _day.bump({"spaeter": "spaeter", "zurueck": "zurueck"}.get(name, "erledigt"))
    _live(f"{name} {x['art']}")
    print(f"vorgang: knopf {name} {x['art']} ok | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return dict(extra, item=public(uid, y), rev=_load(uid)["rev"])


def _source_act(uid, x, name):
    """The source's own function behind a button (its own checks and journal lines)."""
    import fuerdich
    k = x["key"].split(":", 1)[1]
    if name in ("erledigt", "ausblenden"):
        fuerdich.mark(uid, k, "done" if name == "erledigt" else "no", tell=False)
        return None
    if name == "zurueck":
        fuerdich.mark(uid, k, "open", tell=False)
        return None
    src = fuerdich.find(uid, k)
    if src is None:
        raise _refuse("quelle_fehlt", 404, "Die Mail dazu ist gerade nicht gelesen. Bitte unter E-Mail → Für dich neu lesen.")
    if name == "fd_remind":
        item = fuerdich.remind(uid, src)
        fuerdich.mark(uid, k, "done", tell=False)
        return {"text": item["text"], "due": item["due"]}
    if name == "fd_more":
        import ichweiss
        return {"name": ichweiss.set_state(uid, src["who"], "yes", "karte")["name"]}
    if name == "fd_cancel":
        import datetime as dt
        return {"draft": fuerdich.cancel_draft(uid, src, dt.date.today())}
    return None


def _refuse(why, status, text):
    _bump_refused()
    print(f"vorgang: knopf abgelehnt grund={why}", flush=True)
    return HTTPException(status, text)


def _bump_refused():
    _day.bump("abgelehnt")


# ---------------------------------------------------------------- every minute (panel.every_minute)
async def due(now=None):
    """Später is over → open again, once into today's main conversation and onto one device; old ones go."""
    import push
    now = now or time.time()
    if not features.admin_on("vorgaenge"):
        return 0
    back = 0
    c = features.chat_cfg()
    for uid in profiles.user_ids():
        if not os.path.exists(_file(uid)) or not features.allowed("vorgaenge", uid, c):
            continue
        woke = []

        def fn(d):
            keep = []
            for x in d["items"]:
                if x["zustand"] == "spaeter" and x.get("spaeter_bis") and x["spaeter_bis"] <= now:
                    _set(x, "offen", "", "", now)
                    x["wieder"] = int(now)
                    woke.append(dict(x))
                elif x["zustand"] in ("offen", "gesehen") and _stale(x, now):
                    _set(x, "weg", "abgelaufen", "", now)
                if x["zustand"] in ("erledigt", "weg") and now - x["ge"] > ERLEDIGT_TAGE * 86400:
                    continue
                keep.append(x)
            d["items"] = keep
        _mut(uid, fn)
        for x in woke:
            back += 1
            _day.bump("wieder")
            try:
                card_message(uid, dict(x, titel="Wieder da: " + x["titel"]))
                await push.send(uid, "↺ " + x["titel"], ARTEN[x["art"]]["de"], tag="vg-" + x["id"],
                                private=ARTEN[x["art"]]["mail"], why="Offen")
            except Exception as e:
                print("vorgang: wieder da fehler", type(e).__name__, flush=True)
        if woke:
            print(f"vorgang: wieder offen {len(woke)} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return back


def _stale(x, now):
    since = max(x["t"], x.get("wieder", 0))      # one back from „Später“ counts from its return
    if x["art"] == "erinnerung":
        return now - since > ERINNERUNG_STUNDEN * 3600
    if x.get("frist"):
        try:
            return datetime.date.fromisoformat(x["frist"]) < datetime.date.fromtimestamp(now) - datetime.timedelta(days=1)
        except ValueError:
            return False
    return now - since > ALT_TAGE * 86400


# ---------------------------------------------------------------- the sources (stage 1)
def from_reminder(uid, item):
    """profiles.take_reminder: a reminder rang (once for the profile) → a Vorgang „Erinnerung“ with its card."""
    if not features.allowed("vorgaenge", uid):
        return None
    x, _ = put(uid, "erinnerung", "erinnerung:" + str(item.get("id", ""))[:16], "Erinnerung: " + str(item.get("text", "")),
               say=True)
    return x["id"] if x else None


def from_fuerdich(uid, items, today):
    """fuerdich.run: the cards that need the person (fuerdich.URGENT) become Vorgänge, in the Offen list only;
    the conversation gets a card when Von selbst says it (proactive.check_fuerdich)."""
    if not features.allowed("vorgaenge", uid):
        return 0
    import fuerdich
    n = 0
    for x in items:
        if x["kind"] not in fuerdich.URGENT:
            continue
        title, line = fuerdich.sentence(x, today)
        felder = [["Von", x.get("who", "")]] + ([["Betrag", x["amount"]]] if x.get("amount") else [])
        _, new = put(uid, "fuerdich", "fuerdich:" + x["id"], title, line, felder, fuerdich.deadline(x),
                     {"event": fuerdich.event_line(x, today), "ref": x.get("ref", ""), "folder": x.get("box", "INBOX"),
                      "fd": x["id"], "addr": x.get("addr", ""), "subject": x.get("subject", "")})
        n += new
    return n


def find(uid, vid):
    """One Vorgang by its number, or None (zustellung.py: is it still open?)."""
    if not (isinstance(vid, str) and ID.fullmatch(vid)) or not os.path.exists(_file(uid)):
        return None
    return next((y for y in _load(uid)["items"] if y["id"] == vid), None)


def delivered(uid, vid, weg, stufe):
    """zustellung.py: a note about this Vorgang went out (stufe "sofort" or "nachgefasst"); the last few are kept."""
    def fn(d):
        x = next((y for y in d["items"] if y["id"] == vid), None)
        if x is not None:
            x["zugestellt"] = (x.get("zugestellt") or [])[-4:] + [{"weg": _clean(weg, 10), "t": int(time.time()),
                                                                   "stufe": _clean(stufe, 12)}]
        return x is not None
    return _mut(uid, fn) if find(uid, vid) else False


def id_of(uid, key):
    x = next((y for y in _load(uid)["items"] if y["key"] == key), None) if os.path.exists(_file(uid)) else None
    return x["id"] if x else None


# ---------------------------------------------------------------- Zustand → Live (numbers only)
def _live(text):
    try:
        import live
        live.event("Offen", text)
    except Exception:
        pass


def today_counts():
    return {k: v for k, v in _day.today().items() if k != "day"}


def for_live():
    """Live (Kalender node): profiles with something open, open, for later, done today; numbers only."""
    if not features.admin_on("vorgaenge"):
        return {"on": False}
    braucht = spaeter = profs = 0
    for uid in profiles.user_ids():
        if not os.path.exists(_file(uid)):
            continue
        c = counts(_load(uid)["items"])
        braucht += c["braucht"]
        spaeter += c["spaeter"]
        profs += 1 if c["braucht"] or c["spaeter"] else 0
    t = today_counts()
    return {"on": True, "profiles": profs, "braucht": braucht, "spaeter": spaeter, "erledigt": t.get("erledigt", 0),
            "wieder": t.get("wieder", 0), "streams": streams()}


def card(uid):
    """Ich → Heute and the app's Heute: how many need the person and how many wait for later, the first titles."""
    items = _load(uid)["items"]
    need = [x for x in items if group_of(x) == "braucht"]
    return dict(counts(items), first=[x["titel"][:60] for x in sorted(need, key=lambda x: -x["t"])[:3]])


# ---------------------------------------------------------------- endpoints
def _mine(request, prof, rate="vorgaenge"):
    if not features.allowed("vorgaenge", prof["id"]):
        raise HTTPException(403, features.missing_text("vorgaenge", prof["id"]) or "„Alles Offene im Assistenten“ ist aus.")
    guard.limit(request, rate, prof["id"])


@router.get("/api/profile/vorgaenge", dependencies=[Depends(assistant)])
def api_list(request: Request, seit: int = 0, prof=Depends(own_profile)):
    _mine(request, prof)
    return view(prof["id"], max(0, int(seit)))


@router.get("/api/profile/vorgaenge/stream", dependencies=[Depends(assistant)])
async def api_stream(request: Request, prof=Depends(own_profile)):
    uid = prof["id"]
    _mine(request, prof, "vorgaengestream")
    return _hub.stream(uid, lambda: features.allowed("vorgaenge", uid), 30 * 60)


@router.post("/api/profile/vorgaenge/act", dependencies=[Depends(assistant)])
async def api_act(request: Request, prof=Depends(own_profile)):
    _mine(request, prof, "vorgaengeact")
    b = await json_body(request, 2 * 1024)
    vid, name, rev, wann = b.get("id"), b.get("act"), b.get("rev"), b.get("wann", "")
    if not isinstance(vid, str) or not ID.fullmatch(vid) or not isinstance(name, str) or \
            (rev is not None and not isinstance(rev, int)) or not isinstance(wann, str):
        print("vorgang: knopf abgelehnt grund=eingabe", flush=True)
        raise HTTPException(400, "id, act, rev")
    return dict(act(prof["id"], vid, name, rev, wann, _where(request, b)), ok=True)


def _where(request, b):
    if profiles.key_scope(request) == "app":
        return "app"
    return "phone" if b.get("view") == "app" else "web"


@router.post("/api/profile/vorgaenge/seen", dependencies=[Depends(assistant)])
async def api_seen(request: Request, prof=Depends(own_profile)):
    _mine(request, prof, "vorgaengeact")
    b = await json_body(request, 1024)
    ids = b.get("ids")
    if not isinstance(ids, list) or len(ids) > 20 or not all(isinstance(v, str) and ID.fullmatch(v) for v in ids):
        print("vorgang: gesehen abgelehnt grund=eingabe", flush=True)
        raise HTTPException(400, "ids")
    n = sum(1 for v in ids if seen(prof["id"], v, _where(request, b)))
    print(f"vorgang: gesehen {n} | {profiles.log_name(prof)}", flush=True)
    return {"ok": True, "n": n}


@router.delete("/api/profile/vorgaenge", dependencies=[Depends(assistant)])
def api_drop(request: Request, nur: str = "", prof=Depends(own_profile)):
    """Offen → Einstellungen: the done ones away (nur=erledigt) or every Vorgang of this profile; the sources keep
    their own data (a mail, a reminder)."""
    _mine(request, prof, "vorgaengeact")
    if nur not in ("", "erledigt"):
        raise HTTPException(400, "nur")

    def fn(d):
        keep = [x for x in d["items"] if nur and x["zustand"] not in ("erledigt", "weg")]
        n, d["items"] = len(d["items"]) - len(keep), keep
        return n
    n = _mut(prof["id"], fn)
    print(f"vorgang: geloescht {n} {'erledigte' if nur else 'alle'} | {profiles.log_name(prof)}", flush=True)
    return {"ok": True, "n": n}
