"""Finden: Mails und Anhänge (plan such-index, Stufe B; Dominik 2026-10-29 „2a 3a 4a“): every mail of the profile's
mailboxes in the search index of Finden (fund.py), with the text and the fields of its attachments.

- Switch „Mails und Anhänge“ (chat.fund_mail, off), a child of Finden; for every profile that may read mail, never for
  guests. The two sources mail and anhang of fund.QUELLEN follow it.
- Folders: the inbox, the archive and the sent folder (postfach.role: the server's SPECIAL-USE flags first, else the
  usual names), never spam, the trash, drafts or Gmail's views. Only reading: tidy.Box opens each folder with EXAMINE,
  messages are fetched with BODY.PEEK (they stay unread); IMAP only to the profile's own mailboxes (mail.IMAP is
  netguard.IMAP4_SSL).
- All mails, the newest first (2a): per folder UIDVALIDITY, the highest UID read (hoch) and the lowest one read
  backwards so far (tief). Each round reads the new ones above hoch, then, only in quiet minutes (wissen.quiet: a
  minute without a question, nobody speaks) or at night, the older ones below tief, newest first. No cap on the number
  of mails: the round stops with a log line when less than RESERVE_MB stay free on the disk. Another UIDVALIDITY: the
  folder is read anew. Once a day a look at every UID of the folder (SEARCH ALL) takes out what was deleted.
- Slices: one batch takes at most HAPPEN_S seconds of reading (at least one mail) and HAPPEN_N mails and is written in
  one transaction; between two batches vorrang.hold waits while somebody speaks. The round runs in a thread of low
  priority (vorrang.in_thread "Suchindex", started apart by fund.due_once, never on the loop) and has TAG_S seconds by
  day, NACHT_S at night. New mail (mailidle.on_new) starts the profile's next round at once.
- Sealed (3a): subject, excerpt and fields (sender, amount, number, folder role, attachment names) only AES-GCM
  (vorrat.seal through fund.put_sealed), the words only as HMAC marks (vorrat.marke); in plain text stay the source,
  the entry key (mailbox id, a mark of the folder, UID) and the date. Without a key nothing is written.
- Attachments (PDF, Word, OpenDocument, text …, documents.extract_pages, at most ANHANG_MAX bytes and ANHANG_TEXT
  characters): text and fields (amount, invoice number, company by the fixed rules fund.regeln) go into fund, never
  into wissen.db as a document. A scan without text keeps its file name only.
- A hit opens the original in the page E-Mail (finden.js: the mail's folder, then postRead).
- Gone with its mailbox (the next look; a search never shows a mail of a mailbox removed meanwhile), with the switch
  (fund.runde drops the rows), with „Index löschen“ and with the profile (its folder).
- Mail text is written by strangers: data only (fund_suche is under outside and mail, chat.wrap_outside).
- Logs: fund: with fixed words and numbers, the profile as profiles.log_name; Live: mails read today, left, numbers.
"""
import email
import email.policy
import email.utils
import imaplib
import re
import shutil
import threading
import time

import features
import fund
import mail
import profiles
import vorrat
from common import DayCounter

ROLLEN = ("inbox", "archive", "sent")   # postfach.role; never junk, trash, drafts, all
HAPPEN_S = 0.2           # seconds of reading in one batch (at least one mail)
HAPPEN_N = 20            # mails in one batch at most
NEU_S = 15               # seconds a round may take for the new mails (and when called directly)
TAG_S = 30               # ... in a quiet minute by day, with the older mails
NACHT_S = 240            # ... at night (NACHT hours, local time)
NACHT = (1, 6)           # from 01:00 to 06:00 the old mails are read longer
ROUND_S = fund.ROUND_S   # a profile that read its mail lately: a round at most this often
STILL_S = 3600           # ... one that did not: once an hour
QUIET_AGAIN = 60         # with mails left, a quiet minute goes on after this
RESERVE_MB = 2048        # fixed free reserve on the disk: below it the round stops
ANHANG_MAX = 10 * 1024 * 1024   # bytes of an attachment whose text is read
ANHANG_TEXT = 30_000     # characters of an attachment's text kept for its marks and rules
ANHANG_N = 20            # attachments of one mail
FETCH_MOST = ANHANG_MAX * 4 // 3 + 512 * 1024   # bytes of one message fetched (base64 is a third bigger)
_poke = set()            # profiles with new mail (mailidle): their next round at once
_last = {}               # uid -> when the mail round ran last
_left = {}               # uid -> mails left to read (fund_stand), so a quiet minute goes on
_running = set()
_tasks = set()
knapp = {}               # uid -> True while the disk is below the reserve (Einstellungen, Live)
_count = DayCounter(mails=0, anhaenge=0, fehler=0)


def anstossen(uid):
    """mailidle.on_new: new mail in one of the profile's inboxes, its next round comes at once (cheap: a mark)."""
    if features.allowed("fundmail", uid):
        _poke.add(uid)


def _hook():
    try:
        import mailidle
        mailidle.on_new(anstossen)
    except Exception as e:   # the index works without it, five minutes later
        print(f"fund: mail ohne anstoss | {type(e).__name__}", flush=True)


_hook()


def _ruhig(now):
    """May old mails be read now: a quiet minute (wissen.quiet) or the night."""
    import wissen
    return _nacht(now) or wissen.quiet()


def _nacht(now):
    h = time.localtime(now).tm_hour
    return NACHT[0] <= h < NACHT[1]


def aktiv(uid, now):
    return now - mail._used.get(uid, 0) < mail.WARM_SECONDS


def faellig(uid, now):
    """Is a mail round due for this profile: new mail came, its interval passed, or mails are left and it is quiet."""
    if not features.allowed("fundmail", uid):
        return False
    if uid in _poke:
        return True
    last = _last.get(uid, 0)
    if now - last >= (ROUND_S if aktiv(uid, now) else STILL_S):
        return True
    return bool(_left.get(uid)) and now - last >= QUIET_AGAIN and _ruhig(now)


def due(uid, now):
    """fund.due_once: starts the profile's mail round in the background when it is due (not awaited: a long night
    round never holds the panel's other rounds)."""
    import asyncio
    import vorrang
    if uid in _running or not faellig(uid, now) or not mail.get(uid)["accounts"]:
        return False
    _running.add(uid)

    async def go():
        try:
            await vorrang.in_thread("Suchindex", runde, uid, now)
        except Exception as e:
            print(f"fund: runde mail fehler | {type(e).__name__} | {profiles.log_name(profiles.by_id(uid))}", flush=True)
        finally:
            _running.discard(uid)
    task = asyncio.get_running_loop().create_task(go())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return True


def _platz(uid):
    """Is more than RESERVE_MB free where the profile's index lies (fail closed: no answer, no writing)?"""
    try:
        free = shutil.disk_usage(profiles._path()).free
    except OSError:
        return False
    return free >= RESERVE_MB * 1024 * 1024


def _frei_mb():
    try:
        return int(shutil.disk_usage(profiles._path()).free // (1024 * 1024))
    except OSError:
        return 0


def _fkey(uid, aid, name):
    """A folder's part of the entry key: a mark of its name (never the name in plain text)."""
    m = vorrat.marke(uid, f"ordner:{aid}:{name}")
    return m[:8] if m else None


# ---------------------------------------------------------------- state per folder (fund_stand, quelle mail)
def _state(con, aid, fkey):
    pre = fkey + ":"
    return {r["schluessel"][len(pre):]: r["wert"] for r in con.execute(
        "SELECT schluessel, wert FROM fund_stand WHERE quelle='mail' AND konto=? AND schluessel LIKE ?", (aid, pre + "%"))}


def _put_state(con, aid, fkey, st):
    for k, v in st.items():
        con.execute("INSERT OR REPLACE INTO fund_stand (quelle, konto, schluessel, wert) VALUES ('mail',?,?,?)",
                    (aid, f"{fkey}:{k}", str(v)[:400]))


def _drop_folder(con, aid, fkey):
    ids = [r[0] for r in con.execute("SELECT id FROM fund_item WHERE quelle='mail' AND ext LIKE ?", (f"{aid}:{fkey}:%",))]
    n = fund.drop_ids(con, ids)
    con.execute("DELETE FROM fund_stand WHERE quelle='mail' AND konto=? AND schluessel LIKE ?", (aid, fkey + ":%"))
    return n


def ohne_konto(uid, konten):
    """Rows of mailboxes the profile no longer has: gone at once (also its folders' state)."""
    if not fund._exists(uid):
        return 0
    with fund._Db(uid) as con:
        ids = [r[0] for r in con.execute("SELECT id, ext FROM fund_item WHERE quelle IN ('mail','anhang')")
               if r[1].split(":")[0] not in konten]
        n = fund.drop_ids(con, ids) if ids else 0
        con.execute("DELETE FROM fund_stand WHERE quelle='mail' AND konto<>'' AND konto NOT IN (%s)"
                    % ",".join("?" * max(1, len(konten))), list(konten) or [""])
    if n:
        print(f"fund: mail konto entfernt | {n} weg | {profiles.log_name(profiles.by_id(uid))}", flush=True)
    return n


# ---------------------------------------------------------------- one mail into entries
def _anhang_text(name, part, size):
    """The text of an attachment the documents can read, else "" (a scan, a picture, too big, unreadable)."""
    import documents
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if ext not in documents.TYPES or not 0 < size <= ANHANG_MAX:
        return ""
    try:
        pages, _ = documents.extract_pages(name, part.get_payload(decode=True) or b"")
    except Exception:
        return ""
    return "\n".join(t for _, t in pages)[:ANHANG_TEXT]


def eintraege(aid, fkey, rolle, u, msg):
    """(the mail's entry, [its attachments' entries]) for fund.put_sealed; every value from the message is data."""
    ext = f"{aid}:{fkey}:{u}"
    text, _names = mail.plain(msg)
    subject = mail._hdr(msg.get("Subject", ""))
    frm = mail._addr(msg.get("From", ""))
    to = mail._hdr(msg.get("To", ""))[:200]
    when = int(mail._date(msg.get("Date")).timestamp())
    display = email.utils.parseaddr(frm)[0]
    felder, tags = fund.regeln(subject + "\n" + text, {"sender": display})
    # the card shows the address the mail names (never „von Firma X“: no DKIM check), the company only as a tag
    felder.update(absender=frm, ordner=rolle)
    if to and rolle == "sent":
        felder["an"] = to
    anh = []
    for n, (part, name, size) in enumerate(mail.files(msg)[:ANHANG_N]):
        atext = _anhang_text(name, part, size)
        af, at = fund.regeln(atext, {"sender": display})
        af.pop("absender", None)
        af.update(name=name, kb=max(1, size // 1024))
        anh.append({"ext": f"{ext}:{n}", "wann": max(0, when), "titel": name, "auszug": atext, "felder": af, "tags": at,
                    "worte": name + "\n" + atext, "absender": frm})
    if anh:
        felder["anhaenge"] = [a["titel"] for a in anh]
    m = {"ext": ext, "wann": max(0, when), "titel": subject or "(ohne Betreff)", "auszug": text, "felder": felder,
         "tags": tags, "worte": "\n".join([subject, frm, to, text] + [a["titel"] for a in anh]), "absender": frm}
    return m, anh


def _holen(box, u):
    """One message with PEEK (it stays unread), at most FETCH_MOST bytes, or None."""
    typ, data = box.c.uid("FETCH", str(int(u)), f"(BODY.PEEK[]<0.{FETCH_MOST}>)")
    raw = next((p[1] for p in data if isinstance(p, tuple) and p[1]), None) if typ == "OK" else None
    return email.message_from_bytes(raw, policy=email.policy.default) if raw else None


class _Voll(Exception):
    """The disk is below the reserve: the round stops."""


def _lesen(uid, aid, fkey, rolle, box, uids, now, ende):
    """Reads the given UIDs in this order in slices until `ende` (time.monotonic). Returns the UIDs done."""
    import vorrang
    done, i = [], 0
    while i < len(uids) and time.monotonic() < ende:
        vorrang.hold("Suchindex")
        if not _platz(uid):
            raise _Voll()
        t0, batch = time.monotonic(), []
        while i < len(uids) and len(batch) < HAPPEN_N and (not batch or time.monotonic() - t0 < HAPPEN_S):
            u = uids[i]
            i += 1
            msg = _holen(box, u)
            batch.append((u, eintraege(aid, fkey, rolle, u, msg) if msg is not None else None))
        with fund._Db(uid) as con:   # one transaction per slice (the SD card)
            for u, got in batch:
                if got is None:
                    continue
                m, anh = got
                mid = fund.put_sealed(con, uid, "mail", m, now)
                if mid is None:
                    raise RuntimeError("no key")
                old = [r[0] for r in con.execute("SELECT id FROM fund_item WHERE eltern=?", (mid,))]
                fund._drop(con, old)
                for a in anh:
                    fund.put_sealed(con, uid, "anhang", a, now, eltern=mid)
                _count.bump("mails")
                if anh:
                    _count.bump("anhaenge", len(anh))
        done += [u for u, _ in batch]
    return done


def _ordner(uid, aid, box, name, rolle, now, ende, ruhig, who):
    """One folder: the new mails, once a day what was deleted, in quiet minutes the older ones. (new, gone, left)."""
    fkey = _fkey(uid, aid, name)
    validity = box.select(name)
    neu = weg = 0
    with fund._Db(uid) as con:
        st = _state(con, aid, fkey)
        if st.get("validity") and validity and st["validity"] != validity:
            weg += _drop_folder(con, aid, fkey)
            st = {}
            print(f"fund: mail uidvalidity gewechselt | ordner neu | {weg} weg | {who}", flush=True)
        if not st:
            sealed = fund.siegel(uid, "ordner", aid, fkey, name)
            if sealed is None:
                raise RuntimeError("no key")
            st = {"validity": validity, "rolle": rolle, "name": sealed}
            _put_state(con, aid, fkey, st)
    if "hoch" not in st:
        alle = box.search("ALL")
        hoch = max(alle, default=0)
        st.update(hoch=hoch, tief=hoch + 1, rest=len(alle), abgleich=fund._day(now))
    else:
        hoch = int(st["hoch"])
        new = sorted(u for u in box.search("UID", f"{hoch + 1}:*") if u > hoch)
        done = _lesen(uid, aid, fkey, rolle, box, new, now, ende) if new else []
        neu += len(done)
        if done:   # only as far as read without a gap
            k = 0
            while k < len(new) and k < len(done) and new[k] == done[k]:
                k += 1
            st["hoch"] = new[k - 1] if k else hoch
        if st.get("abgleich") != fund._day(now):   # once a day: what was deleted in the mailbox leaves the index
            alle = set(box.search("ALL"))
            with fund._Db(uid) as con:
                gone = [r[0] for r in con.execute("SELECT id, ext FROM fund_item WHERE quelle='mail' AND ext LIKE ?",
                                                  (f"{aid}:{fkey}:%",)) if int(r[1].rsplit(":", 1)[1]) not in alle]
                weg += fund.drop_ids(con, gone) if gone else 0
            st["abgleich"] = fund._day(now)
            st["rest"] = sum(1 for u in alle if u < int(st["tief"]))
    tief = int(st["tief"])
    if ruhig and tief > 1 and time.monotonic() < ende:
        alt = sorted((u for u in box.search("UID", f"1:{tief - 1}") if u < tief), reverse=True)
        done = _lesen(uid, aid, fkey, rolle, box, alt, now, ende) if alt else []
        neu += len(done)
        if done:
            st["tief"] = min(done)
        st["rest"] = max(0, len(alt) - len(done))
        if not alt:
            st["tief"] = 1
    with fund._Db(uid) as con:
        _put_state(con, aid, fkey, {k: v for k, v in st.items() if k in ("hoch", "tief", "rest", "abgleich")})
    return neu, weg, int(st.get("rest") or 0)


def _konto(uid, acct, now, ende, ruhig, who):
    """One mailbox: its inbox, archive and sent folders (never spam or trash); folders gone lose their rows."""
    import postfach
    import tidy
    neu = weg = rest = 0
    with tidy.Box(acct) as box:
        ordner = [(n, postfach.role(box, n)) for n in box.boxes]
        ordner = sorted(((n, r) for n, r in ordner if r in ROLLEN), key=lambda x: (ROLLEN.index(x[1]), x[0]))
        keys = {_fkey(uid, acct["id"], n) for n, _ in ordner}
        with fund._Db(uid) as con:
            old = {r[0].split(":")[0] for r in con.execute("SELECT schluessel FROM fund_stand WHERE quelle='mail' AND konto=?",
                                                         (acct["id"],))}
            for k in old - keys:   # a folder renamed or removed (or no longer one of the three): its mails leave
                weg += _drop_folder(con, acct["id"], k)
        for name, rolle in ordner:
            if time.monotonic() >= ende:
                break
            n, w, r = _ordner(uid, acct["id"], box, name, rolle, now, ende, ruhig, who)
            neu, weg, rest = neu + n, weg + w, rest + r
    return neu, weg


def runde(uid, now=None, secs=None):
    """The mail round of one profile (a worker thread; fund.runde with secs, fundmail.due in the background):
    (new, gone). secs: seconds it may take, by default NACHT_S at night, TAG_S in a quiet minute, else NEU_S."""
    now = time.time() if now is None else now
    if not features.allowed("fundmail", uid):
        return (0, 0)
    who = profiles.log_name(profiles.by_id(uid))
    ruhig = _ruhig(now)
    secs = secs if secs is not None else NACHT_S if _nacht(now) else TAG_S if ruhig else NEU_S
    t0 = time.monotonic()
    ende = t0 + secs
    _last[uid] = now
    _poke.discard(uid)
    accts = mail.get(uid)["accounts"]
    weg = ohne_konto(uid, {a["id"] for a in accts})
    if not accts:
        return (0, weg)
    if vorrat.marke(uid, "probe") is None or vorrat.seal(b"probe", "probe") is None:
        print(f"fund: mail ohne schluessel | nichts geschrieben | {who}", flush=True)
        return (0, weg)
    if not _platz(uid):
        knapp[uid] = True
        print(f"fund: mail platz knapp | {_frei_mb()} MB frei | nichts gelesen | {who}", flush=True)
        return (0, weg)
    neu = 0
    for a in accts:
        if time.monotonic() >= ende:
            break
        try:
            n, w = _konto(uid, a, now, ende, ruhig, who)
            neu, weg = neu + n, weg + w
            knapp.pop(uid, None)
        except _Voll:
            knapp[uid] = True
            print(f"fund: mail platz knapp | {_frei_mb()} MB frei | abgebrochen | {who}", flush=True)
            break
        except RuntimeError:
            print(f"fund: mail ohne schluessel | nichts geschrieben | {who}", flush=True)
            break
        except (ValueError, LookupError, OSError, imaplib.IMAP4.error, EOFError) as e:
            _count.bump("fehler")
            print(f"fund: mail konto fehler | {type(e).__name__} | {who}", flush=True)
    rest = 0
    with fund._Db(uid) as con:
        rest = fund._rest(con)
        con.execute("INSERT OR REPLACE INTO fund_stand (quelle, konto, schluessel, wert) VALUES ('mail','','runde',?)",
                    (str(int(now)),))
    _left[uid] = rest
    fund._live["d"] = None
    if neu or weg:
        print(f"fund: runde mail | {neu} neu | {weg} weg | {rest} offen | {time.monotonic() - t0:.1f} s | {who}", flush=True)
    return (neu, weg)


# ---------------------------------------------------------------- the contract of fund.QUELLEN
def neues_seit(uid, known, budget):
    """The contract's look without writing: mails come through the round of their own (runde), in slices."""
    return [], {}, True


def noch_da(uid, exts):
    """Entries whose mailbox the profile still has (what the mailbox deleted leaves with the daily look)."""
    konten = {a["id"] for a in mail.get(uid)["accounts"]}
    return {e for e in exts if str(e).split(":")[0] in konten}


_names = {}   # (uid, aid, fkey) -> {"name", "rolle"} of the folder (they never change for its key)
_names_lock = threading.Lock()


def _folder(uid, aid, fkey):
    k = (uid, aid, fkey)
    with _names_lock:
        if k in _names:
            return _names[k]
    if not fund._exists(uid):
        return None
    with fund._Db(uid) as con:
        st = _state(con, aid, fkey)
    name = fund.offen(uid, "ordner", aid, fkey, st.get("name", "")) or None
    if not name:
        return None
    got = {"name": name, "rolle": st.get("rolle") or "folder"}
    with _names_lock:
        if len(_names) > 2000:
            _names.clear()
        _names[k] = got
    return got


def weg(uid, ext):
    """How a hit opens: the mail in its folder on the page E-Mail (an attachment: its mail, with its number)."""
    parts = str(ext).split(":")
    if len(parts) < 3 or not re.fullmatch(r"m[0-9a-f]{8}", parts[0]) or not parts[2].isdigit():
        return {}
    f = _folder(uid, parts[0], parts[1])
    if not f:
        return {}
    out = {"art": "mail", "id": f"{parts[0]}:{parts[2]}", "folder": "INBOX" if f["rolle"] == "inbox" else f["name"],
           "rolle": f["rolle"]}
    if len(parts) == 4 and parts[3].isdigit():
        out.update(art="anhang", n=int(parts[3]))
    return out


def for_live():
    """Live: the switch, mails and attachments read today, rounds that failed, the disk below the reserve (numbers)."""
    c = _count.counts()
    return {"on": features.admin_on("fundmail"), "heute": c["mails"], "anhaenge": c["anhaenge"], "fehler": c["fehler"],
            "platz": bool(knapp)}
