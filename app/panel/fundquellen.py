"""Finden, Stufe C (plan such-index; Dominik 2026-10-29): the remaining own sources of the search index of Finden
(fund.py): appointments, contacts, conversations, lists, reminders, pictures and songs. Each follows a sub-switch of
Finden (off by default) and the function it comes from; never for guests.

- termin (Termine finden, chat.fund_termine, needs Kalender): the own calendars only, read from the Spark's copy
  (kalenderspiegel, a Spark calendar from sparkkalender), never a request to a calendar server of its own. Sealed like
  mail: title, place and an excerpt AES-GCM (fund.put_sealed), the words only as HMAC marks; per object the etag as
  its state (as a mark). Calendars shared by others stay out (their owner decides there, calendars.reading).
- kontakt (Kontakte finden, chat.fund_kontakte, needs Kontakte): name, company, title and city of each card from the
  sealed copy (contacts.cards), sealed like mail; never a number, an address or a mail address.
- chat (Gespräche finden, chat.fund_chats, needs Frühere Gespräche): per conversation only its date, channel
  (Telegram, Siri, Uhr …) and number of questions; its words stay in convos.json and are searched through
  recall.liste (BM25 of recall, answers from mail stay out). The title is read from the conversation when shown.
- liste and erinnerung (Listen und Erinnerungen finden, chat.fund_listen, needs Listen or Timer und Erinnerungen): the
  own lists on the Spark and the lists others share with the profile (only through tasks.shared_to, while sharing is
  allowed for both), one entry per list with its open and ticked entries; each reminder with its text and time. Clear
  like their source (tasks.json, reminders.json are not sealed either).
- bild and musik (Bilder und Musik finden, chat.fund_medien, needs Bilder malen or Musik machen): wish, prompt or
  caption of each picture and song (their index.json), clear like their source.
- Incremental: a state per entry (etag, a hash of the fields); a round finds what changed (fund.runde), what is gone
  leaves. fund._stamp asks stempel() whether any of the files moved (mtime), so an idle profile costs nothing.
- Logs: the lines of fund.runde (fund: runde termin | 3 neu | 0 weg | …), fixed words and numbers only.
"""
import datetime
import hashlib
import json
import os
import re

import features
import fund
import profiles
import vorrat

TEXT = 2000              # characters of an appointment's description read for its marks
KANAL = {"telegram": ("Telegram", "Telegram"), "siri": ("Siri", "Siri"), "desk": ("Begleiter", "Companion"),
         "watch": ("Uhr", "Watch"), "speaker": ("Lautsprecher", "Speaker"), "telefon": ("Telefon", "Phone"),
         "": ("Panel", "Panel")}


def _h(*parts):
    return hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).hexdigest()


def _stand_siegel(uid, *parts):
    """The state of a sealed entry: a mark of its hash (an equal entry is seen as unchanged, nothing readable)."""
    return vorrat.marke(uid, "#" + _h(*parts)[:40])


def _sec(t):
    try:
        t = float(t or 0)
    except (TypeError, ValueError):
        return 0
    return int(t / 1000 if t > 1e11 else t)


def _one(text, n):
    return re.sub(r"\s+", " ", str(text or "")).strip()[:n]


# ---------------------------------------------------------------- termin (kalenderspiegel, sparkkalender)
def _kalender(uid):
    """[(entry id, entry name, calendar url, {href: [etag, text, lo, hi]})] of the profile's OWN calendars, from the
    Spark's copy only. A copy that is not there yet gives nothing (fund then keeps what it has)."""
    import calendars
    import kalenderspiegel
    import sparkkalender
    out = []
    for c in calendars.get(uid)["calendars"]:
        cid = str(c.get("id") or "")
        if not kalenderspiegel.CID.fullmatch(cid):
            continue
        if c.get("spark"):
            cal = sparkkalender.calendar(uid, cid) or {}
            out.append((cid, c.get("name") or "", "spark", dict(cal.get("items") or {})))
            continue
        for url, cal in list((kalenderspiegel._load(cid) or {}).items()):
            for _ in range(3):   # the loop may change the copy meanwhile: read it again
                try:
                    out.append((cid, c.get("name") or "", url, dict(cal.get("items") or {})))
                    break
                except RuntimeError:
                    continue
    return out


def kalender_ids(uid):
    """The ids of the profile's own calendar entries now (a search never shows an appointment of one just removed)."""
    import calendars
    return [str(c.get("id") or "") for c in calendars.get(uid)["calendars"]]


def _ext_termin(cid, url, href):
    return f"{cid}:{_h(url, href)[:16]}"


def _epoch(v, zone):
    if not isinstance(v, datetime.datetime):
        v = datetime.datetime.combine(v, datetime.time())
    if v.tzinfo is None:
        v = v.replace(tzinfo=zone)
    return int(v.timestamp())


def _vevent(text, zone):
    """(title, place, description, start, all day) of an object's first appointment, or None."""
    import icalendar
    try:
        cal = icalendar.Calendar.from_ical(text)
    except Exception:
        return None
    evs = [e for e in cal.walk("VEVENT") if e.get("DTSTART") is not None]
    if not evs:
        return None
    ev = next((e for e in evs if e.get("RECURRENCE-ID") is None), evs[0])
    s = ev.get("DTSTART").dt
    return (_one(ev.get("SUMMARY"), 160), _one(ev.get("LOCATION"), fund.MAX_TAG), _one(ev.get("DESCRIPTION"), TEXT),
            _epoch(s, zone), not isinstance(s, datetime.datetime))


def termin_neu(uid, known, budget):
    if not vorrat.marke(uid, "probe"):
        return [], {}, True      # without a key nothing sealed can be written
    zone = fund.zone()
    out = []
    for cid, name, url, items in _kalender(uid):
        for href, x in items.items():
            if not isinstance(x, (list, tuple)) or len(x) < 2:
                continue
            ext = _ext_termin(cid, url, href)
            st = _stand_siegel(uid, x[0] or _h(x[1]))
            if known.get(ext) == st:
                continue
            if len(out) >= budget:
                return out, {}, False
            ev = _vevent(str(x[1])[:256 * 1024], zone)
            if not ev:
                continue
            titel, ort, text, start, ganz = ev
            out.append({"ext": ext, "wann": start, "titel": titel or "Termin",
                        "auszug": " · ".join(p for p in (ort, text) if p)[:fund.AUSZUG],
                        "felder": {"ort": ort, "kalender": _one(name, 60), "ganztag": ganz}, "stand": st,
                        "tags": [("ort", ort, 1)] if len(ort) >= 2 else [], "worte": " ".join((titel, ort, text))})
    return out, {}, True


def termin_da(uid, exts):
    if not vorrat.marke(uid, "probe"):
        return set(exts)          # no key: nothing can be compared, nothing is dropped
    have = {_ext_termin(cid, url, href) for cid, _, url, items in _kalender(uid) for href in items}
    return {e for e in exts if e in have}


# ---------------------------------------------------------------- kontakt (contacts.cards)
def _karten(uid):
    import contacts
    out = {}
    for x in contacts.cards(uid):
        if isinstance(x, dict) and x.get("name"):
            out[str(x.get("id") or contacts._vid(x))[:200]] = x
    return out


def _stadt(x):
    return next((_one(a.get("city"), fund.MAX_TAG) for a in x.get("addrs") or [] if isinstance(a, dict) and a.get("city")), "")


def kontakt_neu(uid, known, budget):
    if not vorrat.marke(uid, "probe"):
        return [], {}, True
    out = []
    for cid, x in _karten(uid).items():
        name, org, stadt = _one(x.get("name"), fund.MAX_TAG), _one(x.get("org"), fund.MAX_TAG), _stadt(x)
        nick, titel = _one(x.get("nick"), 60), _one(x.get("title"), 120)
        st = _stand_siegel(uid, name, org, stadt, nick, titel)
        if known.get(cid) == st:
            continue
        if len(out) >= budget:
            return out, {}, False
        tags = [("person", name, 1)] + ([("firma", org, 1)] if len(org) >= 2 else []) + ([("ort", stadt, 1)] if len(stadt) >= 2 else [])
        out.append({"ext": cid, "wann": 0, "titel": name, "auszug": " · ".join(p for p in (org, titel, stadt) if p),
                    "felder": {"firma": org, "ort": stadt}, "stand": st, "tags": tags,
                    "worte": " ".join((name, nick, org, titel, stadt)), "absender": " ".join((name, nick, org))})
    return out, {}, True


def kontakt_da(uid, exts):
    if not vorrat.marke(uid, "probe"):
        return set(exts)
    have = set(_karten(uid))
    return {e for e in exts if e in have}


# ---------------------------------------------------------------- chat (convos.json through recall)
def _kanal(c):
    via = next((m.get("via") for m in c.get("msgs") or [] if isinstance(m, dict) and m.get("via") in KANAL), "")
    return via or ""


def chat_neu(uid, known, budget):
    out = []
    for c in profiles.convos(uid):
        if not isinstance(c, dict) or not c.get("id"):
            continue
        n = sum(1 for m in c.get("msgs") or [] if isinstance(m, dict) and m.get("role") == "user")
        if not n:
            continue
        via = _kanal(c)
        st = json.dumps([int(c.get("updated") or 0), n, via])
        if known.get(c["id"]) == st:
            continue
        if len(out) >= budget:
            return out, {}, False
        de, en = KANAL[via]
        # only date, channel and count: the conversation's words stay in convos.json (recall.liste finds them)
        out.append({"ext": str(c["id"])[:80], "wann": _sec(c.get("updated")), "titel": "", "auszug": "",
                    "felder": {"kanal": de, "fragen": n}, "stand": st, "tags": [], "worte": f"{de} {en}"})
    return out, {}, True


def chat_da(uid, exts):
    have = {str(c.get("id")) for c in profiles.convos(uid) if isinstance(c, dict)}
    return {e for e in exts if e in have}


def chat_zeigen(uid, ext):
    """(title, excerpt) of a conversation when it is shown, read from convos.json then (never copied into fund.db)."""
    c = next((c for c in profiles.convos(uid) if isinstance(c, dict) and str(c.get("id")) == ext), None)
    if not c:
        return "", ""
    first = next((m.get("content") for m in c.get("msgs") or [] if isinstance(m, dict) and m.get("role") == "user"), "")
    return _one(c.get("title") or first, 160), _one(first, fund.AUSZUG)


# ---------------------------------------------------------------- liste (tasks.json, own and shared) and erinnerung
def _listen(uid):
    """[(ext, name, [entries])] of the profile's lists on the Spark and of the lists others share with it (only what
    tasks.shared_to grants: sharing allowed for both, the share still there)."""
    import tasks
    d = tasks._load(uid)
    out = []
    for li in tasks.lists_of(uid, d):
        if li["id"] in d["targets"]:
            continue   # a list kept in a calendar account lives there (no request of its own)
        out.append((li["id"], li["name"], [x for x in d["items"] if x["list"] == li["id"] and not x.get("sent")]))
    for owner, oname, li, _lvl in tasks.shared_to(uid):
        od = tasks._load(owner)
        if li["id"] in od["targets"]:
            continue
        out.append((f"{owner}.{li['id']}", f"{oname} · {li['name']}",
                    [x for x in od["items"] if x["list"] == li["id"] and not x.get("sent")]))
    return out


def liste_neu(uid, known, budget):
    import tasks
    out = []
    for ext, name, items in _listen(uid):
        offen = [tasks.show(x) for x in items if not x.get("done")]
        fertig = [tasks.show(x) for x in items if x.get("done")]
        st = _h(name, offen, fertig)[:32]
        if known.get(ext) == st:
            continue
        if len(out) >= budget:
            return out, {}, False
        out.append({"ext": ext, "wann": max([_sec(x.get("t")) for x in items] or [0]), "titel": _one(name, 160),
                    "auszug": ", ".join(offen)[:fund.AUSZUG], "felder": {"offen": len(offen), "erledigt": len(fertig)},
                    "stand": st, "tags": [], "worte": " ".join([name] + offen + fertig)})
    return out, {}, True


def liste_da(uid, exts):
    have = {ext for ext, _, _ in _listen(uid)}
    return {e for e in exts if e in have}


def erinnerung_neu(uid, known, budget):
    out = []
    for x in profiles.reminders(uid):
        if not isinstance(x, dict) or not x.get("id"):
            continue
        st = _h(x.get("text"), x.get("due"), x.get("every"))[:32]
        if known.get(str(x["id"])) == st:
            continue
        if len(out) >= budget:
            return out, {}, False
        text = _one(x.get("text"), 200)
        out.append({"ext": str(x["id"])[:40], "wann": _sec(x.get("due")), "titel": text[:160], "auszug": "",
                    "felder": {"wiederholt": x["every"]} if x.get("every") else {}, "stand": st, "tags": [], "worte": text})
    return out, {}, True


def erinnerung_da(uid, exts):
    have = {str(x.get("id")) for x in profiles.reminders(uid) if isinstance(x, dict)}
    return {e for e in exts if e in have}


# ---------------------------------------------------------------- bild and musik (their index.json)
def bild_neu(uid, known, budget):
    import bilder
    out = []
    for x in bilder.all_pics(uid):
        wish, prompt = _one(x.get("wish"), 300), _one(x.get("prompt"), 1000)
        st = _h(wish, prompt, x.get("art"), x.get("t"))[:32]
        if known.get(x["id"]) == st:
            continue
        if len(out) >= budget:
            return out, {}, False
        foto = x.get("art") == "foto" or x.get("src") == "foto"
        out.append({"ext": x["id"], "wann": _sec(x.get("t")), "titel": (wish or prompt or ("Foto" if foto else "Bild"))[:160],
                    "auszug": prompt[:fund.AUSZUG] if wish else "", "felder": {"format": _one(x.get("format"), 20)},
                    "stand": st, "tags": [("kategorie", "Foto", 1)] if foto else [], "worte": f"{wish} {prompt}"})
    return out, {}, True


def bild_da(uid, exts):
    import bilder
    have = {x["id"] for x in bilder.all_pics(uid)}
    return {e for e in exts if e in have}


def musik_neu(uid, known, budget):
    import musik
    out = []
    for x in musik.all_songs(uid):
        wish, cap, lyr = _one(x.get("wish"), 300), _one(x.get("caption"), 600), _one(x.get("lyrics"), TEXT)
        st = _h(wish, cap, lyr, x.get("t"))[:32]
        if known.get(x["id"]) == st:
            continue
        if len(out) >= budget:
            return out, {}, False
        out.append({"ext": x["id"], "wann": _sec(x.get("t")), "titel": (wish or cap or "Lied")[:160],
                    "auszug": cap[:fund.AUSZUG] if wish else "", "felder": {}, "stand": st, "tags": [],
                    "worte": f"{wish} {cap} {lyr}"})
    return out, {}, True


def musik_da(uid, exts):
    import musik
    have = {x["id"] for x in musik.all_songs(uid)}
    return {e for e in exts if e in have}


# ---------------------------------------------------------------- what a round depends on
def stempel(uid, names):
    """The files the sources of Stufe C come from, as (name, mtime) for the sources the profile may use: unchanged,
    fund.due_once skips the profile (no work every five minutes)."""
    import kalenderspiegel
    files = []
    if "termin" in names:
        files += [os.path.join(kalenderspiegel.DIR, cid + ".json") for cid in kalender_ids(uid)
                  if kalenderspiegel.CID.fullmatch(cid)] + [profiles._path(uid, "spark-kalender.json"),
                                                            profiles._path(uid, "calendar.json")]
    if "kontakt" in names:
        files.append(profiles._path(uid, "contacts.json"))
    if "liste" in names:
        files.append(profiles._path(uid, "tasks.json"))
        import tasks
        files += [profiles._path(o, "tasks.json") for o, _, _, _ in tasks.shared_to(uid)]
    if "erinnerung" in names:
        files.append(profiles._path(uid, "reminders.json"))
    if "bild" in names:
        import bilder
        files.append(bilder._index_file(uid))
    if "musik" in names:
        import musik
        files.append(musik._index_file(uid))
    out = []
    for f in files:
        try:
            out.append((f, os.stat(f).st_mtime_ns))
        except OSError:
            out.append((f, None))
    # the conversations are read through profiles.convos (sealed, read_own keeps them in memory): ids and times
    if "chat" in names:
        out.append(("chat", _h(sorted((str(c.get("id")), c.get("updated")) for c in profiles.convos(uid)
                                     if isinstance(c, dict)))[:16]))
    # the calendar copy may live in memory only for a while: its etags count too
    if "termin" in names:
        out.append(("termin", _h(sorted((cid, url, len(items)) for cid, _, url, items in _kalender(uid)))[:16]))
    return tuple(out)


def frei(uid, quelle):
    """Whether the function a source comes from is allowed for the profile (besides its sub-switch of Finden)."""
    need = {"termin": ("calendar",), "kontakt": ("contacts",), "chat": ("history",), "liste": ("tasks",),
            "erinnerung": ("reminders",), "bild": ("bilder",), "musik": ("musik",)}.get(quelle, ())
    return all(features.allowed(k, uid) for k in need)
