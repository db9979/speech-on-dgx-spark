"""Gemerkt-Hinweis (plan nutzerwissen, Punkt 1, Dominik 2026-10-29 „a“ zu Frage 5): what the Spark keeps about a person
is seen at once and can be taken back.

1. memory_save in a conversation (chat_tools.py): the event {"type": "memory", "action": "saved"} carries the fact's
   "id", its "rev" (rev_of: a fingerprint of the fact as it was saved) and "undo" (whether there is something to take
   back). chat.js draws the chip „✓ Gemerkt: … · Rückgängig · Ansehen“ under the answer and keeps it with the message
   (msgs[i].mem = [{id, rev}], numbers only, profiles._clean_msg via clean); the text comes from Ich → Gedächtnis
   when it is drawn again, so every device shows it (verlauf). The Begleiter gets a card with „Rückgängig“ (it sends
   „Mach das rückgängig“: aendern.undo calls take_back below) and „Ansehen“; the iPhone draws the chip itself.
2. Learned by itself (chat.learn_once, src auto, after a quiet conversation): the person is mostly gone, so no line in
   the old conversation but one card through vorgaenge.put (kind CARD, key „gemerkt:<convo>“, at most CARD_MAX facts
   as lines, the ids and revs in daten "fakten"): „Stimmt“ confirms them (gedaechtnis.confirm), „Rückgängig“ takes
   them back (take_back), „Ansehen …“ opens Ich → Gedächtnis. Not urgent, never said (say=False): it stands in the
   line „Noch offen“ above the next conversation, under Offen and as a number on the card Gedächtnis of Heute
   (today.py). After OFFEN_TAGE days the card goes; the fact stays „gelernt, nicht bestätigt“.
3. Rückgängig: POST /api/profile/memory/{id}/undo {"rev"}: only while the fact is unchanged since rev (else 409
   „inzwischen geändert“), only the own profile's facts (the file is the session's own). A new fact goes, a fixed place
   it gave a new wording gets its earlier version back (profiles.undo_fact). The card's button and „Mach das
   rückgängig“ run the same take_back.

The card's title goes with a push („Wieder da“ after „Später“) and so maybe to Telegram: it holds only fixed words and
a number („Spark hat sich 2 Dinge gemerkt“), never the text of a fact. Logs and Live: fixed words and numbers only.
Admin switch chat.memory_note (features.DEFAULT_ON with its reason); it holds for every profile the admin did not
block; guests have no memory and get nothing of this.
"""
import datetime
import hashlib
import json
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Request

import features
import guard
import profiles
from common import DayCounter
from core import assistant, browser_profile, json_body

router = APIRouter()

FEATURE = "gedhinweis"
CARD = "gemerkt"
CARD_MAX = 3            # facts on one card („bis zu 3 Fakten als Felder“)
MEM_MAX = 3             # chips kept with one answer
OFFEN_TAGE = 7          # the card goes after this (the fact stays learned, unconfirmed)
WEG = "Ich → Gedächtnis"
FID = re.compile(r"[0-9a-f]{8}")
REV = re.compile(r"[0-9a-f]{12}")
# what came of a take_back, in fixed words for the person (and the HTTP status of the ones that did not work); the
# pages translate them (i18n.js), the iPhone has them in Localizable.xcstrings
SAY = {"geloescht": "Vergessen.", "zurueckgeholt": "Frühere Fassung wieder da.",
       "geaendert": "Inzwischen geändert – unter Ich → Gedächtnis ansehen.",
       "fehlt": "Diesen Eintrag gibt es nicht mehr.", "gleich": "Da gibt es nichts zurückzunehmen."}
STATUS = {"geaendert": 409, "fehlt": 404, "gleich": 409}
WO = ("chip", "karte", "sprache", "app", "begleiter")

_day = DayCounter(chip=0, karte=0, rueckgaengig=0, stimmt=0, abgelehnt=0)   # Zustand → Live, numbers only


def rev_of(f):
    """The fact as it was saved, as a short fingerprint: any change of wording, source, confirmation or time changes it
    (a topic set later does not). Never sent anywhere but to the own profile's pages."""
    keep = [f.get("id"), f.get("text"), f.get("src"), f.get("created"), f.get("changed"), f.get("confirmed"),
            bool(f.get("auto"))]
    return hashlib.sha256(json.dumps(keep, ensure_ascii=False).encode()).hexdigest()[:12]


def what(f):
    """What remember just did to f: "neu" (a new fact), "platz" (a fixed place got this new wording) or "" (the same
    wording said again: nothing to take back)."""
    if not f.get("changed"):
        return "neu"
    prev = [p for p in f.get("prev") or [] if isinstance(p, dict)]
    return "platz" if prev and prev[0].get("until") == f["changed"] and prev[0].get("text") != f.get("text") else ""


def clean(mem):
    """The chips kept with a message (profiles._clean_msg): only well formed numbers, at most MEM_MAX."""
    out = []
    for x in mem if isinstance(mem, list) else []:
        if isinstance(x, dict) and FID.fullmatch(str(x.get("id", ""))) and REV.fullmatch(str(x.get("rev", ""))):
            out.append({"id": x["id"], "rev": x["rev"]})
    return out[:MEM_MAX]


def _find(uid, text):
    """The fact remember kept for text (it returns the text it kept, a fixed place keeps it as its wording)."""
    return next((f for f in profiles.memory(uid) if f.get("text") == text), None)


def note(uid, text):
    """chat_tools memory_save: what the event carries for the chip ({} while the switch is off or the fact is gone)."""
    if not features.allowed(FEATURE, uid):
        return {}
    f = _find(uid, text)
    if f is None:
        return {}
    _day.bump("chip")
    return {"id": f["id"], "rev": rev_of(f), "undo": bool(what(f))}


def take_back(uid, fact_id, rev, wo="chip"):
    """Rückgängig: the same for the chip, the card and „Mach das rückgängig“. Only while the fact is unchanged since
    rev. Returns "geloescht" | "zurueckgeholt" | "geaendert" | "fehlt" | "gleich"; one journal line for each."""
    fact_id, rev, wo = str(fact_id or ""), str(rev or ""), wo if wo in WO else "chip"
    who = profiles.log_name(profiles.by_id(uid))
    if not FID.fullmatch(fact_id) or not REV.fullmatch(rev):
        how = "fehlt"
    else:
        how = profiles.undo_fact(uid, fact_id, lambda f: rev_of(f) == rev)
    if how in ("geloescht", "zurueckgeholt"):
        _day.bump("rueckgaengig")
        print(f"gedaechtnis: rueckgaengig {how} | weg={wo} | {who}", flush=True)
    else:
        _day.bump("abgelehnt")
        print(f"gedaechtnis: rueckgaengig abgelehnt grund={how} | weg={wo} | {who}", flush=True)
    return how


# ---------------------------------------------------------------- learned by itself: the card
def _key(convo_id):
    return f"{CARD}:{convo_id}"


def _facts_of(x):
    """[(id, rev)] a card keeps in daten "fakten"."""
    out = []
    for part in str((x.get("daten") or {}).get("fakten") or "").split(","):
        fid, _, rev = part.partition(":")
        if FID.fullmatch(fid) and REV.fullmatch(rev):
            out.append((fid, rev))
    return out[:CARD_MAX]


def _valid(uid, pairs, facts=None):
    """The card's facts that are still as they were learned: [(fact, rev)]."""
    facts = profiles.memory(uid) if facts is None else facts
    by = {f["id"]: f for f in facts}
    return [(by[fid], rev) for fid, rev in pairs if fid in by and rev_of(by[fid]) == rev]


def title(n):
    """Fixed words and a number only: the title may go out with a push („Wieder da“) and to Telegram."""
    return "Spark hat sich etwas gemerkt" if n == 1 else f"Spark hat sich {n} Dinge gemerkt"


def learned(uid, convo, texts, now=None):
    """chat.learn_once: the facts it kept from one quiet conversation become (or join) one card „Gemerkt von selbst“.
    Returns the number of facts on the card (0: nothing, switch off or Offen off)."""
    import vorgaenge
    if not features.allowed(FEATURE, uid) or not texts:
        return 0
    now = time.time() if now is None else now
    facts = profiles.memory(uid)
    new = [(f["id"], rev_of(f)) for f in (next((y for y in facts if y.get("text") == t), None) for t in texts)
           if f is not None and what(f)]
    if not new:
        return 0
    cid = str(convo.get("id") or "")
    if not re.fullmatch(r"[\w\-]{1,40}", cid):
        return 0
    old = vorgaenge.find(uid, vorgaenge.id_of(uid, _key(cid)) or "")
    keep = _facts_of(old) if old and old.get("zustand") not in ("erledigt", "weg") else []
    pairs = [(f["id"], r) for f, r in _valid(uid, [p for p in keep if p[0] not in {n[0] for n in new}] + new, facts)]
    pairs = pairs[-CARD_MAX:]
    if not pairs:
        return 0
    import chat
    zone = chat.user_zone(profiles.effective(uid).get("tz", ""))
    try:
        hm = datetime.datetime.fromtimestamp(int(convo.get("updated") or now * 1000) / 1000, zone).strftime("%H:%M")
    except (ValueError, OverflowError, OSError):
        hm = ""
    by = {f["id"]: f for f in facts}
    x, made = vorgaenge.put(uid, CARD, _key(cid), title(len(pairs)),
                            ("Von selbst aus deinem Gespräch" + (f" von {hm}" if hm else "") + ". Stimmt das?"),
                            felder=[("Gemerkt", by[fid]["text"]) for fid, _ in pairs],
                            daten={"weg": WEG, "fakten": ",".join(f"{a}:{b}" for a, b in pairs)}, wieder=True, now=now)
    if x is None:
        return 0
    _day.bump("karte")
    print(f"gedaechtnis: gemerkt-karte {'neu' if made else 'ergaenzt'} fakten={len(pairs)} | "
          f"{profiles.log_name(profiles.by_id(uid))}", flush=True)
    return len(pairs)


def open_count(uid):
    """Heute → Gedächtnis: how many facts learned by itself wait on open cards (a number, never a fact)."""
    import vorgaenge
    if not features.allowed(FEATURE, uid) or not features.allowed("vorgaenge", uid):
        return 0
    items = vorgaenge._load(uid)["items"]
    return sum(len(_facts_of(x)) for x in items if x["art"] == CARD and vorgaenge.group_of(x) == "braucht")


def _card_acts(uid, x):
    """„Stimmt“ and „Rückgängig“ only while a fact of the card is as it was learned; „Ansehen …“ always."""
    ok = features.allowed(FEATURE, uid) and bool(_valid(uid, _facts_of(x)))
    return {"gm_stimmt", "gm_weg", "oeffnen"} if ok else {"oeffnen"}


def _card_run(uid, x, name):
    """A button of the card; the card closes through vorgaenge.done with how it ended."""
    import gedaechtnis
    import vorgaenge
    if name not in ("gm_stimmt", "gm_weg"):
        return None
    if not features.allowed(FEATURE, uid):
        raise vorgaenge.HTTPException(403, "Der Gemerkt-Hinweis ist für dich nicht freigegeben.")
    valid = _valid(uid, _facts_of(x))
    if not valid:
        raise vorgaenge.HTTPException(409, SAY["geaendert"])
    who = profiles.log_name(profiles.by_id(uid))
    if name == "gm_stimmt":
        n = sum(bool(gedaechtnis.confirm(uid, f["id"])) for f, _ in valid)
        _day.bump("stimmt", n)
        print(f"gedaechtnis: gemerkt-karte stimmt fakten={n} | {who}", flush=True)
        vorgaenge.done(uid, x["key"], "bestaetigt")
        return {"text": "Bestätigt." if n else SAY["fehlt"]}
    hows = [take_back(uid, f["id"], rev, "karte") for f, rev in valid]
    n = sum(h in ("geloescht", "zurueckgeholt") for h in hows)
    vorgaenge.done(uid, x["key"], "rueckgaengig")
    return {"text": f"Rückgängig gemacht: {n}." if n else SAY["geaendert"]}


def _register():
    import vorgaenge
    vorgaenge.ARTEN[CARD] = {"de": "Gemerkt von selbst", "en": "Remembered by itself", "sym": "check", "mail": False,
                             "dringend": False, "acts": ("gm_stimmt", "gm_weg", "oeffnen")}
    vorgaenge.AKTIONEN.update(gm_stimmt={"de": "Stimmt", "en": "That's right", "stufe": "direkt"},
                              gm_weg={"de": "Rückgängig", "en": "Undo", "stufe": "direkt"})
    vorgaenge.QUELLEN[CARD] = {"acts": _card_acts, "run": _card_run}
    vorgaenge.OFFEN_STUNDEN[CARD] = OFFEN_TAGE * 24


_register()


# ---------------------------------------------------------------- Zustand → Live (numbers only)
def for_live(now=None):
    """Live node Gedächtnis: today's chips, cards, take-backs, confirmations, refusals; never a fact."""
    if not features.admin_on(FEATURE):
        return {"on": False}
    return dict({k: v for k, v in _day.today(now).items() if k != "day"}, on=True)


# ---------------------------------------------------------------- endpoint
@router.post("/api/profile/memory/{fact_id}/undo", dependencies=[Depends(assistant)])
async def api_undo(fact_id: str, request: Request, prof=Depends(browser_profile)):
    """The chip's „Rückgängig“ {"rev", "wo"?}: the own profile's fact only, only while it is unchanged since rev."""
    guard.limit(request, "memory", uid=prof["id"])
    body = await json_body(request, 256)
    if not features.allowed(FEATURE, prof["id"]):
        raise HTTPException(403, features.missing_text(FEATURE, prof["id"]) or "Der Gemerkt-Hinweis ist aus.")
    b = body if isinstance(body, dict) else {}
    how = take_back(prof["id"], str(fact_id)[:40], str(b.get("rev") or "")[:40], str(b.get("wo") or "chip"))
    if how in STATUS:
        raise HTTPException(STATUS[how], SAY[how])
    return {"how": how, "text": SAY[how]}
