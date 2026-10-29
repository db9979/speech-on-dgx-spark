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
    from_pending()  stage 2: a proposal waiting for a yes (calendars, senden, tidy: profiles.pending_set) becomes the
                card „Wartet auf dein Ja“ with what it is and its yes button; ja() runs the module's own carry (the same
                as a typed „Ja“), sweep() closes the card when the proposal is answered, replaced or over

    GET  /api/profile/vorgaenge?seit=<rev>   the changed ones (all without seit), with "rev" and the counts
    DELETE /api/profile/vorgaenge?nur=erledigt  the done ones (or all) of this profile away
    GET  /api/profile/vorgaenge/stream       {"type": "vorgang", "rev": n, "neu": bool, "weg": bool}: never text
    POST /api/profile/vorgaenge/act          {"id", "act", "rev", "wann"?}: one button (vs_ja: {"text", "gelungen"})

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

# the kinds (stage 1: Für dich and reminders; stage 2 proposals of Kalender and E-Mail; stage 3 people and mail:
# Nachrichten, Geteiltes, Wichtige Mail; stage 4 Dienste for admins, Aufträge, MCP-Freigaben)
ARTEN = {
    "fuerdich": {"de": "Für dich", "en": "For you", "sym": "mail", "mail": True, "dringend": False,
                 "acts": ("fd_remind", "fd_event", "fd_reply", "fd_cancel", "fd_more", "erledigt", "ausblenden")},
    "erinnerung": {"de": "Erinnerung", "en": "Reminder", "sym": "bell", "mail": False, "dringend": True,
                   "acts": ("erledigt",)},
    # stage 2: a proposal waiting for a yes (calendars, senden, tidy); it lives as long as the proposal does
    "vorschlag": {"de": "Wartet auf dein Ja", "en": "Waiting for your yes", "sym": "check", "mail": False, "dringend": False,
                  "acts": ("vs_ja", "vs_aendern", "vs_nein")},
    # a task from a meeting in the Begleiter, put onto a list (thread „Besprechungs-Aufgaben in Listen“, Dominik
    # 2026-10-20 „ok“ 4a): one card per task, only under Offen (say=False); „Erledigt“ ticks the entry off, the list
    # ticking it off closes the card (tasks.card_follows); overdue stays open
    "besprechung": {"de": "Aus Besprechung", "en": "From a meeting", "sym": "check", "mail": False, "dringend": False,
                    "acts": ("erledigt", "ausblenden")},
    # stage 3: new chat messages while no page was open (chats._notify), one card per chat, only under Offen; reading
    # the chat closes it (chats.read), a new message opens it again
    "nachricht": {"de": "Nachricht", "en": "Message", "sym": "chat", "mail": False, "dringend": False,
                  "acts": ("cx_antworten", "cx_gelesen")},
    # something shared with this profile (geteilt.tell): one card per sharing profile and kind
    "geteilt": {"de": "Geteilt", "en": "Shared", "sym": "share", "mail": False, "dringend": False,
                "acts": ("oeffnen", "erledigt")},
    # an important new mail (proactive.check_mail, Von selbst „Wichtige Mail“): its card goes with the note;
    # „Nicht wichtig“ also puts its sender on the profile's list (proactive._card_act, no card from it any more)
    "mail": {"de": "Wichtige Mail", "en": "Important mail", "sym": "mail", "mail": True, "dringend": False,
             "acts": ("ml_lesen", "fd_reply", "erledigt", "ausblenden")},
    # stage 4: a watched service is down or warns (dienstwacht, admins only); it closes itself when the service is
    # fine again, „Ansehen“ opens Zustand → Überblick, nothing is restarted from a card
    "dienst": {"de": "Dienst", "en": "Service", "sym": "warn", "mail": False, "dringend": True,
               "acts": ("oeffnen", "erledigt")},
    # a running job asks a question (auftragsplan._wait); answered on Ich → Aufträge, the answer closes it
    "auftrag": {"de": "Auftrag fragt", "en": "Job asks", "sym": "spark", "mail": False, "dringend": True,
                "acts": ("oeffnen",)},
    # an MCP program wants an action (mcpserver.propose); only Ich → Spark als MCP-Server confirms, never a card
    "freigabe": {"de": "Freigabe", "en": "Approval", "sym": "check", "mail": False, "dringend": True,
                 "acts": ("oeffnen",)},
}
# a source module's own buttons for its kind (a new art in ARTEN, its buttons in AKTIONEN): {"acts": fn(uid, x) -> the
# buttons its rules allow now, "run": fn(uid, x, name) -> dict for the answer or None}; raising HTTPException refuses.
# The module registers itself (QUELLEN["regel"] = {...}); act() still checks owner, kind, state, rev and Notaus first.
QUELLEN = {}
# how long a card of a kind stays open at most (hours) before it goes as „Abgelaufen“; the others: ALT_TAGE
OFFEN_STUNDEN = {"erinnerung": 12, "freigabe": 0.25, "auftrag": 1, "dienst": 24}
# how a source closed a card (done(wie)): these count as „weg“, every other one as „erledigt“
WEG_WIE = ("ausblenden", "abgelaufen", "abgelehnt")
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
    # "ja": the card itself is the preview, the button is the yes (the same carry as a typed „Ja“)
    "vs_ja": {"de": "Ja", "en": "Yes", "stufe": "ja"},
    "vs_aendern": {"de": "Ändern …", "en": "Change …", "stufe": "seite"},
    "vs_nein": {"de": "Abbrechen", "en": "Cancel", "stufe": "direkt"},
    # stage 3+4: opening the place where it goes on (daten "weg", a fixed way of the panel; "chat", "ref")
    "oeffnen": {"de": "Ansehen …", "en": "Show …", "stufe": "seite"},
    "cx_antworten": {"de": "Antworten …", "en": "Reply …", "stufe": "seite"},
    "cx_gelesen": {"de": "Gelesen", "en": "Read", "stufe": "direkt"},
    "ml_lesen": {"de": "Lesen …", "en": "Read …", "stufe": "seite"},
}
# Stufe 2 (plan Kalender und E-Mail): the proposals that become a card „Wartet auf dein Ja“: the name of the waiting
# file (profiles.pending_set) → the module with card(uid, p) and its yes (calendars.carry, senden.carry, tidy.carry_out)
VORSCHLAEGE = {"calendar": "calendars", "senden": "senden", "mail": "tidy"}
# the yes button's word and what the card says after it, by the module's card()["knopf"]
KNOPF = {"eintragen": (("Eintragen", "Add"), ("Eingetragen", "Added")),
         "verschieben": (("Verschieben", "Move"), ("Verschoben", "Moved")),
         "loeschen": (("Löschen", "Delete"), ("Gelöscht", "Deleted")),
         "senden": (("Senden", "Send"), ("Gesendet", "Sent")),
         "ablegen": (("Als Entwurf ablegen", "Save as draft"), ("Als Entwurf abgelegt", "Saved as draft")),
         "ausfuehren": (("Ausführen", "Do it"), ("Ausgeführt", "Done"))}
# „Später“: the four choices of the card (plan 4a), local time of the profile; "ohne" stays in Offen only
SPAETER = {"abend": ("Heute Abend", "This evening"), "morgen": ("Morgen früh", "Tomorrow morning"),
           "woche": ("Nächste Woche", "Next week"), "ohne": ("Ohne Zeit", "No time")}
ABEND, MORGEN = 18, 8
ZUSTAENDE = ("offen", "gesehen", "spaeter", "erledigt", "weg")
ERLEDIGT_TAGE = 7               # done and gone ones stay this long under „Erledigt“ (with „Zurückholen“)
ALT_TAGE = 30                   # an open one without a deadline goes after this ("weg")
MAX_ITEMS = 300
# what a button that opens a page needs (Für dich: the calendar line, the mail's number, folder, sender, subject);
# a sender and a subject are outside text, shown and handed on as text only; "fakten" the ids and revs of the facts
# on a card „Gemerkt von selbst“ (gemerkt.py, numbers only)
DATEN = ("event", "ref", "folder", "fd", "addr", "subject", "chat", "weg", "fakten")
MAX_TEXT = 160
FELD_MAX = 600                  # a line of a card: the text of a mail to send is read before „Senden“
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
profiles.PENDING_HOOKS.append(lambda uid, name, item: from_pending(uid, name, item))


def _clean(v, n=MAX_TEXT):
    return re.sub(r"[\x00-\x1f]+", " ", str(v or "")).strip()[:n]


# ---------------------------------------------------------------- making and closing
def put(uid, art, key, titel, zeile="", felder=(), frist="", daten=None, say=False, now=None, knopf="", wieder=False):
    """Makes the Vorgang of key (or updates the words of the one there is). Returns (item, new) or (None, False) when
    the function is off for this profile. say: a new one also goes as a card into today's main conversation.
    knopf: the yes button's word of a proposal (KNOPF). wieder: a done one of the same key opens again and counts as
    new (a new chat message after reading, a second share of the same profile)."""
    if not features.allowed("vorgaenge", uid) or art not in ARTEN or not KEY.fullmatch(str(key)):
        return None, False
    now = now or time.time()
    words = {"titel": _clean(titel), "zeile": _clean(zeile),
             "felder": [[_clean(a, 30), _clean(b, FELD_MAX)] for a, b in list(felder)[:6]], "frist": _clean(frist, 10),
             "daten": {k: _clean(v, 300) for k, v in (daten or {}).items() if k in DATEN},
             **({"knopf": knopf} if knopf in KNOPF else {})}

    def fn(d):
        x = next((y for y in d["items"] if y["key"] == key), None)
        if x is not None and wieder and x["zustand"] in ("erledigt", "weg"):
            x.update(words)
            _set(x, "offen", now=now)
            x["t"] = int(now)
            return x, True
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
    if x.get("art") == "vorschlag" and zustand in ("erledigt", "weg"):   # a mail's text is kept only while it waits
        x["felder"] = [f for f in x.get("felder", []) if f[0] != "Text"]


def done(uid, key, wie="erledigt", wo=""):
    """The source says the thing is done (or not wanted) somewhere else; nothing when there is no such Vorgang."""
    if not os.path.exists(_file(uid)):
        return False

    def fn(d):
        x = next((y for y in d["items"] if y["key"] == key and y["zustand"] not in ("erledigt", "weg")), None)
        if x:
            _set(x, "weg" if wie in WEG_WIE else "erledigt", wie, wo)
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
    names = {k: AKTIONEN[k] for k in acts}
    if x.get("knopf") in KNOPF:      # a proposal's yes says what it does („Eintragen“, „Senden“)
        names["vs_ja"] = dict(AKTIONEN["vs_ja"], de=KNOPF[x["knopf"]][0][0], en=KNOPF[x["knopf"]][0][1])
    return {"id": x["id"], "art": x["art"], "art_de": a["de"], "art_en": a["en"], "sym": a["sym"],
            "dringend": a["dringend"], "mail": a["mail"], "titel": x["titel"], "zeile": x.get("zeile", ""),
            "felder": x.get("felder", []), "frist": x.get("frist", ""), "zustand": x["zustand"], "gruppe": group_of(x),
            "spaeter_bis": x.get("spaeter_bis", 0), "t": x["t"], "ge": x["ge"], "wie": x.get("wie", ""),
            "wo": x.get("wo", ""), "rev": x.get("rev", 0), "daten": x.get("daten", {}),
            "acts": [{"k": k, "de": names[k]["de"], "en": names[k]["en"], "stufe": names[k]["stufe"]} for k in acts],
            "zugestellt": x.get("zugestellt", []),
            **({"fertig": list(KNOPF[x["knopf"]][1])} if x.get("knopf") in KNOPF else {})}


def knoepfe(uid, vid):
    """The buttons a short note may carry (Telegram, Begleiter): the open Vorgang's direct ones and „Später“ with
    „Morgen früh“; the ones that open a page or need the preview (Ja) stay on the card. [] when none."""
    x = next((y for y in _load(uid)["items"] if y["id"] == vid), None)
    if x is None or x["zustand"] in ("erledigt", "weg") or x["art"] == "vorschlag":
        return []
    ok = _allowed_acts(uid, x)
    return [(k, AKTIONEN[k]["de"]) for k in ARTEN[x["art"]]["acts"] + ("spaeter",)
            if k in ok and AKTIONEN[k]["stufe"] == "direkt"]


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
    if x["art"] == "vorschlag":      # no „Später“ and no way back: the proposal itself is gone after 15 minutes
        return set() if x["zustand"] in ("erledigt", "weg") else {"vs_ja", "vs_nein"} | ({"vs_aendern"} if x.get("aendern") else set())
    if x["zustand"] in ("erledigt", "weg"):
        return {"zurueck"}
    out = {"erledigt", "spaeter"} | ({"zurueck"} if x["zustand"] == "spaeter" else set())
    if x["art"] == "besprechung":      # „Nicht wichtig“ hides the card, the entry stays on the list
        out.add("ausblenden")
    if x["art"] in ("nachricht", "geteilt", "mail", "dienst", "auftrag", "freigabe"):   # stages 3+4: the kind's own buttons
        out |= set(ARTEN[x["art"]]["acts"])
        if x["art"] == "mail" and not features.allowed("mailsend", uid):   # a reply only where mail may be written
            out.discard("fd_reply")
    if x["art"] in QUELLEN:
        out |= set(QUELLEN[x["art"]]["acts"](uid, x))
    if x["art"] == "fuerdich":
        out.add("ausblenden")
        import fuerdich
        src = fuerdich.find(uid, x["key"].split(":", 1)[1])
        for k in (fuerdich.acts(uid, src) if src else []):
            out.add("fd_" + k)
    return out


# ---------------------------------------------------------------- the buttons
WO = {"web": "Rechner", "phone": "Handy", "app": "iPhone", "desk": "Begleiter", "tg": "Telegram"}


def _check(uid, vid, name, rev, wann=""):
    """Every button's checks (name, Notaus, owner, rev, kind, state); returns (the file, the Vorgang)."""
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
    return d, x


def act(uid, vid, name, rev=None, wann="", wo="web", now=None):
    """Runs one button. Returns {"item", "rev", ...}; raises HTTPException with a fixed sentence when it may not.
    The yes of a proposal (vs_ja) runs in ja(), it waits for the calendar or the outgoing server."""
    d, x = _check(uid, vid, name, rev, wann)
    now = now or time.time()
    where = WO.get(wo, "Rechner")
    if x["art"] == "vorschlag":
        return _vorschlag_act(uid, x, name, where, now)
    extra = (_source_act(uid, x, name) or {}) if x["art"] in ("fuerdich", "besprechung", "nachricht") and name != "spaeter" else \
        (QUELLEN[x["art"]]["run"](uid, x, name) or {}) if x["art"] in QUELLEN and name not in ("spaeter", "zurueck") else {}
    if AKTIONEN[name]["stufe"] == "seite":
        print(f"vorgang: knopf {name} seite {x['art']} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
        return dict(extra, item=public(uid, x), rev=d["rev"])

    def fn(d2):
        y = next((z for z in d2["items"] if z["id"] == vid), None)
        if y is None:
            return None
        if name in ("erledigt", "fd_remind", "fd_more", "cx_gelesen"):
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
    if x["art"] == "besprechung":
        return _meeting_act(uid, x, name)
    if x["art"] == "nachricht":     # „Gelesen“: the chat itself counts it read (its own checks, the sender sees it)
        if name == "cx_gelesen":
            import chats
            try:
                chats.read(uid, x["key"].split(":", 1)[1])
            except LookupError:
                raise _refuse("quelle_fehlt", 404, "Diesen Chat gibt es nicht mehr.")
        return None
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
        return {"name": ichweiss.more(uid, src["who"])["name"]}
    if name == "fd_cancel":
        import datetime as dt
        return {"draft": fuerdich.cancel_draft(uid, src, dt.date.today())}
    return None


def _meeting_act(uid, x, name):
    """A meeting task's card: „Erledigt“ ticks its entry off, „Zurückholen“ brings it back (tasks.tick_from_card);
    „Nicht wichtig“ only hides the card, the entry stays on the list."""
    import tasks
    _, lst, eid = x["key"].split(":", 2)
    if name in ("erledigt", "zurueck"):
        try:
            tasks.tick_from_card(uid, lst, eid, "done" if name == "erledigt" else "undo")
        except notaus.NotausAktiv:
            raise _refuse("notaus", 503, "Notaus: gerade wird nichts geändert.")
    return None


def from_meeting(uid, lst, list_name, entries, when):
    """begleiter.py, a meeting's tasks onto a list: one card per new entry [(entry id, text, due)] under Offen, never
    into the conversation (say=False). when: "20.10. 14:00", the meeting's start. Returns how many are new."""
    import tasks
    n = 0
    for eid, text, due in entries:
        _, new = put(uid, "besprechung", tasks.card_key(lst, eid), text, f"Besprechung {when}",
                     [["Liste", list_name]], due or "", say=False)
        n += new
    return n


# ---------------------------------------------------------------- Stufe 2: a proposal waiting for a yes
def _mod(name):
    import importlib
    return importlib.import_module(VORSCHLAEGE[name])


def _who(uid):
    return profiles.log_name(profiles.by_id(uid))


def _may(uid, name):
    """The module's own switches, checked again at the press (the admin may have switched it off since)."""
    if name == "calendar":
        return features.allowed("calendar", uid)
    if name == "senden":
        import senden
        return senden.level() != "off" and features.allowed("mailsend", uid) and features.allowed("mail", uid)
    return features.allowed("tidy", uid) and features.allowed("mail", uid)


def from_pending(uid, name, item):
    """profiles.pending_set: a proposal of calendars, senden or tidy waits for a yes → the card „Wartet auf dein Ja“
    (in Offen and under the answer that made it, chat.py). A newer one of the same module replaces it."""
    if name not in VORSCHLAEGE or not features.allowed("vorgaenge", uid):
        return None
    c = _mod(name).card(uid, item)
    key = f"vorschlag:{name}:{int(item.get('t') or 0)}"

    def fn(d):
        for y in d["items"]:
            if y["art"] == "vorschlag" and y["key"].startswith(f"vorschlag:{name}:") and y["key"] != key \
                    and y["zustand"] in ("offen", "gesehen"):
                _set(y, "weg", "ersetzt")
    _mut(uid, fn)
    x, _ = put(uid, "vorschlag", key, c["titel"], felder=c["felder"], knopf=c["knopf"])
    if x:   # the file was just written: its card waits (also one of the same second that closed before)
        def mark(d):
            y = next((z for z in d["items"] if z["id"] == x["id"]), None)
            if y and y["zustand"] in ("erledigt", "weg"):
                _set(y, "offen")
            if y:
                y["aendern"] = bool(c.get("aendern"))
        _mut(uid, mark)
    return x["id"] if x else None


def _proposal(uid, x):
    """(name, the waiting proposal, its module) of a card; the card goes when the proposal is gone (410)."""
    _, name, t = x["key"].split(":", 2)
    if name not in VORSCHLAEGE:
        raise _refuse("art", 403, "Für diesen Vorgang gibt es diesen Knopf nicht.")
    mod = _mod(name)
    p = mod.pending(uid)
    if not p or str(int(p.get("t") or 0)) != t:
        sweep(uid)
        raise _refuse("vorbei", 410, "Der Vorschlag gilt nicht mehr. Sag es dem Assistenten bitte noch einmal.")
    if not _may(uid, name):
        raise _refuse("aus", 403, "Diese Funktion ist gerade aus.")
    return name, p, mod


def _close(uid, vid, zustand, wie, where, now=None):
    def fn(d):
        y = next((z for z in d["items"] if z["id"] == vid), None)
        if y:
            _set(y, zustand, wie, where, now)
        return y
    return _mut(uid, fn)


def _vorschlag_act(uid, x, name, where, now):
    """„Abbrechen“ (the proposal goes, nothing is done) and „Ändern …“ (it goes to the page's form or writing
    window, already filled; only the page saves or sends). The yes runs in ja()."""
    if name == "vs_ja":
        raise _refuse("weg", 400, "Diesen Knopf gibt es so nicht.")
    pname, p, mod = _proposal(uid, x)
    profiles.pending_drop(uid, pname)
    extra = {}
    if name == "vs_aendern":
        extra = mod.card(uid, p).get("aendern") or {}
        extra = {"event": extra["event"]} if "event" in extra else {"draft": {"to": extra.get("addr", ""),
                                                                               "subject": extra.get("subject", ""),
                                                                               "text": extra.get("text", "")}}
    y = _close(uid, x["id"], "weg", name, where, now)
    _day.bump("erledigt")
    _live(f"{name} vorschlag")
    print(f"vorgang: knopf {name} vorschlag ok | {_who(uid)}", flush=True)
    return dict(extra, item=public(uid, y), rev=_load(uid)["rev"])


async def ja(uid, vid, rev=None, wo="web"):
    """The yes button of a proposal: the same carry as a typed „Ja“ (calendars.carry, senden.carry, tidy.carry_out),
    from any own device, also when the proposal was made at a speaker or in Telegram (plan 7a „Am Handy freigeben“).
    Returns {"item", "rev", "text", "gelungen"}: the module's checked result in the panel's words."""
    import asyncio
    _, x = _check(uid, vid, "vs_ja", rev)
    name, p, mod = _proposal(uid, x)
    profiles.pending_drop(uid, name)      # one yes carries it out once, whichever device was quicker
    if name == "calendar":
        ok, res = await mod.carry(uid, p)
        text = (res if p.get("change") else f"Eingetragen in „{res}“.") if ok else f"Nicht ausgeführt: {res}"
    elif name == "senden":
        how, why = await mod.carry(uid, p)
        ok = how == "sent"
        text = {"sent": f"Die Mail an {p.get('label', '')} ist gesendet.", "notaus": "Notaus: gerade wird nichts gesendet.",
                "refused": f"Nicht gesendet: {why}", "failed": "Der Postausgang brach ab; ob die Mail raus ist, steht im "
                "Ordner Gesendet."}[how]
    else:
        try:
            ok, text = True, await asyncio.to_thread(mod.carry_out, uid, p)
        except Exception as e:
            ok, text = False, f"Nicht ausgeführt: {str(e)[:120] if isinstance(e, ValueError) else type(e).__name__}"
    y = _close(uid, x["id"], "erledigt" if ok else "weg", "vs_ja" if ok else "fehler", WO.get(wo, "Rechner"))
    _day.bump("erledigt" if ok else "abgelehnt")
    if ok:
        _day.bump("ja")
    _live(f"vs_ja vorschlag {'ok' if ok else 'fehler'}")
    print(f"vorgang: knopf vs_ja vorschlag {'ok' if ok else 'fehler'} | {_who(uid)}", flush=True)
    return {"item": public(uid, y), "rev": _load(uid)["rev"], "text": _clean(text, 300), "gelungen": ok}


def sweep(uid, now=None):
    """The cards of proposals that are gone (answered in the conversation, replaced, older than their minutes) are
    closed: „Im Gespräch beantwortet“ or „Abgelaufen“. chat_turn after every answer, due() every minute."""
    if not os.path.exists(_file(uid)):
        return 0
    now = now or time.time()
    gone = {}
    for x in _load(uid)["items"]:
        if x["art"] != "vorschlag" or x["zustand"] not in ("offen", "gesehen"):
            continue
        _, name, t = x["key"].split(":", 2)
        mod = _mod(name) if name in VORSCHLAEGE else None
        p = mod.pending(uid) if mod else None
        if not p or str(int(p.get("t") or 0)) != t:
            gone[x["id"]] = "abgelaufen" if not mod or now - int(t) >= getattr(mod, "PENDING_SECONDS", 900) else "beantwortet"
    if not gone:
        return 0

    def fn(d):
        for y in d["items"]:
            if y["id"] in gone and y["zustand"] in ("offen", "gesehen"):
                _set(y, "weg", gone[y["id"]], "", now)
    _mut(uid, fn)
    print(f"vorgang: vorschlag vorbei {len(gone)} | {_who(uid)}", flush=True)
    return len(gone)


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
        sweep(uid, now)
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
    if x["art"] in OFFEN_STUNDEN:
        return now - since > OFFEN_STUNDEN[x["art"]] * 3600
    if x["art"] == "besprechung":      # a task stays open while its entry is (overdue too); the list closes it
        return False
    if x.get("frist"):
        try:
            return datetime.date.fromisoformat(x["frist"]) < datetime.date.fromtimestamp(now) - datetime.timedelta(days=1)
        except ValueError:
            return False
    return now - since > ALT_TAGE * 86400


# ---------------------------------------------------------------- „Was ist offen?“ (stage 4, read only)
# The question by voice or typed: the panel lists the open cards itself (newest and urgent first), the model only
# says it. Nothing is closed by the tool; that stays with the cards' buttons. Titles may hold a sender or a subject
# (outside text): the answer of this turn is treated like one made from mail (no tool that changes anything after).
WORDS = re.compile(r"(?i)\b(was (ist|steht|liegt) (noch )?(offen|an)|was (ist|bleibt) (noch )?zu tun|"
                   r"(noch )?offene (sachen|punkte|vorgänge|karten)|was braucht mich|(hab(e)? ich|gibt es) (noch )?was offen(es)?|"
                   r"what('s| is) (still )?open|anything open)\b")
OFFEN_TOOL = {"type": "function", "function": {
    "name": "offen_zeigen",
    "description": "Lists what is still open for the user on the page Offen (cards of mails, reminders, proposals, "
                   "messages, shares, questions of jobs): how many, the newest titles, how many wait for later. Read "
                   "only; closing goes with the cards' buttons. Use it when the user asks what is still open or to do.",
    "parameters": {"type": "object", "properties": {}}}}
OFFEN_HINT = ("Fragt jemand, was noch offen ist oder was ihn braucht, ruf offen_zeigen und antworte nur aus dessen "
              "Ergebnis. Erledigen geht nur mit den Knöpfen der Karten.")
OFFEN_MAX = 8


def offer(ctx):
    """Only in the profile's own session, only with the function on, only when the words ask what is open."""
    who = ctx.get("who")
    if not who or not ctx.get("own") or ctx.get("private") is False or ctx.get("client") == "mcp":
        return None
    if not features.allowed("vorgaenge", who["id"]) or not WORDS.search(str(ctx.get("text") or "")):
        return None
    return {"tools": [OFFEN_TOOL], "hint": OFFEN_HINT, "keep": {"offen_zeigen"}, "mail": {"offen_zeigen"},
            "filler": {"offen_zeigen": ("Ich schaue, was offen ist.", "Let me see what is open.")}}


def offen_text(uid):
    """The panel's own sentence: the number, up to OFFEN_MAX titles (urgent and newest first), the later ones."""
    items = _load(uid)["items"]
    need = sorted((x for x in items if group_of(x) == "braucht"), key=lambda x: (not ARTEN[x["art"]]["dringend"], -x["t"]))
    later = sum(1 for x in items if group_of(x) == "spaeter")
    if not need:
        return "Nichts offen." + (f" Für später zurückgelegt: {later}." if later else "")
    rows = [f"{ARTEN[x['art']]['de']}: {x['titel']}" + (f" ({x['zeile']})" if x.get("zeile") else "") for x in need[:OFFEN_MAX]]
    more = len(need) - len(rows)
    return (f"Offen: {len(need)}. " + "; ".join(rows) + "." + (f" Dazu {more} weitere." if more > 0 else "")
            + (f" Für später zurückgelegt: {later}." if later else "") + " Alles steht unter Offen, mit Knöpfen.")


async def tool(name, args, ctx):
    uid = (ctx.get("who") or {}).get("id")
    if name != "offen_zeigen" or not uid or not features.allowed("vorgaenge", uid):
        print("vorgang: werkzeug abgelehnt | aus", flush=True)
        return "Alles Offene im Assistenten ist aus."
    out = offen_text(uid)
    print(f"vorgang: werkzeug offen | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return out


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
    braucht = spaeter = profs = warten = 0
    arten = {}           # the open ones by kind (stages 3+4: Nachricht, Geteilt, Wichtige Mail, Dienst …)
    for uid in profiles.user_ids():
        if not os.path.exists(_file(uid)):
            continue
        items = _load(uid)["items"]
        c = counts(items)
        warten += sum(1 for x in items if x["art"] == "vorschlag" and group_of(x) == "braucht")
        for x in items:
            if group_of(x) == "braucht":
                arten[x["art"]] = arten.get(x["art"], 0) + 1
        braucht += c["braucht"]
        spaeter += c["spaeter"]
        profs += 1 if c["braucht"] or c["spaeter"] else 0
    t = today_counts()
    return {"on": True, "profiles": profs, "braucht": braucht, "spaeter": spaeter, "erledigt": t.get("erledigt", 0),
            "wieder": t.get("wieder", 0), "streams": streams(), "warten": warten, "ja": t.get("ja", 0),
            "arten": {ARTEN[k]["de"]: arten[k] for k in ARTEN if arten.get(k)}}


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
    if name == "vs_ja":
        return dict(await ja(prof["id"], vid, rev, _where(request, b)), ok=True)
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
