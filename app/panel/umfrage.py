"""Umfragen in Chats (Nextcloud-Ideen 4, Dominik 2026-11-15 „alles umsetzen“; Idee aus Nextcloud Talk, nur als Idee,
kein Code; Bild /mnt/project-files/nextcloud-ideen/bauplan.png): eine Frage mit 2 bis MAX_OPTS Antworten als Nachricht
in einem Chat dieses Sparks (zu zweit oder Gruppe, nie privat verschlüsselt, nie mit anderen Sparks).

- Jedes Mitglied stimmt ab (eine Antwort, mit „Mehrere erlaubt“ mehrere) und ändert seine Stimme, bis die Umfrage
  zu ist; wer abgestimmt hat, sehen alle Mitglieder (Namen wie im Chat), nie jemand außerhalb.
- Schließen kann nur, wer sie gestellt hat; dann zählt nichts mehr.
- Frage und Antworten liegen versiegelt in der Nachricht wie jeder Chat-Text (chats.seal); Stimmen nur als
  Profil-Nummer → Antwort-Nummern. Zurücknehmen der Nachricht nimmt die Umfrage mit.

Admin-Schalter chat.chats_polls (aus, baut auf Chats); nie ein Werkzeug fürs Modell, nur Knöpfe auf der Seite Chats
und in den Apps. Journal (Bereich Nachrichten): „chats: poll made | options n“, „chats: poll vote“, „chats: poll closed“.
Termin finden (Stufe 3b) legt seine Abstimmung als dieselbe Umfrage an (art "termin", die Antworten sind Zeiten).
"""
import time

from fastapi import APIRouter, Depends, Request

import chats
import features
from common import DayCounter
from core import assistant, json_body

KEY = "umfrage"
MAX_OPTS = 10
MAX_OPT = 120             # characters of one answer
_count = DayCounter(gestellt=0, stimmen=0)
ON_CLOSE = {}             # art -> f(uid, cid, mid, poll, winner index) when a poll of that art is closed (Termin finden)


def _make(uid, cid, opts, multi, art, data):
    def extra(mid):
        return {"poll": {"opts": [chats.seal(o, cid, f"{mid}/o{i}") for i, o in enumerate(opts)], "multi": bool(multi),
                         "votes": {}, "closed": 0, "art": art, **({"data": data(mid) if callable(data) else data} if data else {})}}
    return extra


async def stellen(uid, cid, question, options, multi=False, art="", data=None, now=None, mark="📊 "):
    """Puts a poll into the chat: the question as the message's text, 2 to MAX_OPTS answers. Returns the message."""
    if not features.allowed(KEY, uid):
        raise PermissionError(("Umfragen sind für dich aus. " + features.missing_text(KEY, uid)).strip())
    q = chats.clean(question, 300)
    opts = [chats.clean(o, MAX_OPT) for o in (options if isinstance(options, list) else [])][:MAX_OPTS + 1]
    opts = [o for o in opts if o]
    if not q:
        raise ValueError("Bitte eine Frage eingeben.")
    if not 2 <= len(opts) <= MAX_OPTS or len(set(o.lower() for o in opts)) != len(opts):
        raise ValueError(f"Bitte 2 bis {MAX_OPTS} verschiedene Antworten.")
    item = await chats.send(uid, cid, mark + q, now=now, extra=_make(uid, cid, opts, multi, art, data))
    _count.bump("gestellt")
    chats._log("poll made", options=len(opts))
    return item


def _poll(d, mid):
    x = next((x for x in d["items"] if x["id"] == mid and not x.get("gone")), None)
    if not x or not isinstance(x.get("poll"), dict):
        raise LookupError("no such poll")
    return x, x["poll"]


def abstimmen(uid, cid, mid, picks, now=None):
    """The member's vote (answer numbers; [] takes it back) while the poll is open."""
    if not features.allowed(KEY, uid):
        raise PermissionError(("Umfragen sind für dich aus. " + features.missing_text(KEY, uid)).strip())
    chats._member(uid, cid)
    picks = sorted({int(i) for i in picks if isinstance(i, int) and not isinstance(i, bool)}) if isinstance(picks, list) else None
    if picks is None:
        raise ValueError("Bitte eine Antwort wählen.")

    def f(meta, d, _):
        x, p = _poll(d, mid)
        if p.get("closed"):
            raise PermissionError("Die Umfrage ist schon zu.")
        if any(not 0 <= i < len(p["opts"]) for i in picks) or (len(picks) > 1 and not p.get("multi")):
            raise ValueError("Diese Antwort gibt es nicht.")
        if picks:
            p["votes"][uid] = picks
        else:
            p["votes"].pop(uid, None)
        return meta["members"]
    members = chats._mutate(cid, f, now)
    _count.bump("stimmen")
    chats._log("poll vote", picks=len(picks))
    chats._tell(members, {"type": "chat", "id": cid})


def schliessen(uid, cid, mid, now=None):
    """Only who asked closes it; then nothing counts any more. Returns the winning answer's number (most votes,
    the first on a tie) or -1 without a vote."""
    chats._member(uid, cid)
    now = time.time() if now is None else now

    def f(meta, d, _):
        x, p = _poll(d, mid)
        if x["from"] != uid:
            raise PermissionError("Schließen kann nur, wer gefragt hat.")
        if p.get("closed"):
            raise PermissionError("Die Umfrage ist schon zu.")
        p["closed"] = now
        n = counts(p)
        win = max(range(len(n)), key=lambda i: (n[i], -i)) if any(n) else -1
        p["win"] = win
        return meta["members"], dict(p), win
    members, p, win = chats._mutate(cid, f, now)
    chats._log("poll closed", votes=len(p["votes"]))
    chats._tell(members, {"type": "chat", "id": cid})
    hook = ON_CLOSE.get(p.get("art") or "")
    if hook:
        hook(uid, cid, mid, p, win)
    return win


def counts(p):
    n = [0] * len(p["opts"])
    for picks in p["votes"].values():
        for i in picks:
            if 0 <= i < len(n):
                n[i] += 1
    return n


def public(x, cid, uid, names):
    """chats.PUBLIC: the poll as the page and the apps show it."""
    p = x.get("poll")
    if not isinstance(p, dict):
        return None
    mid = x["id"]
    who = [[] for _ in p["opts"]]
    for u, picks in p["votes"].items():
        for i in picks:
            if 0 <= i < len(who):
                who[i].append(names.get(u, ""))
    return {"poll": {"opts": [chats.unseal(o, cid, f"{mid}/o{i}") for i, o in enumerate(p["opts"])],
                     "n": counts(p), "who": who, "mine": p["votes"].get(uid, []), "multi": bool(p.get("multi")),
                     "closed": bool(p.get("closed")), "win": p.get("win", -1) if p.get("closed") else -1,
                     "art": p.get("art", ""), "can_close": x["from"] == uid and not p.get("closed"),
                     "voters": len(p["votes"]), **({"data": p["data"]} if p.get("data") else {})}}


def for_live():
    """Zustand → Live, node Chats: polls made and votes today (numbers only)."""
    c = _count.counts()
    return {"on": bool(features.chat_cfg().get("chats_polls")), "gestellt": c["gestellt"], "stimmen": c["stimmen"]}


chats.PUBLIC.append(public)
chats.LIVE["umfrage"] = lambda: for_live()
chats.STATE["polls"] = lambda uid: features.allowed(KEY, uid)


# ---------------------------------------------------------------- API (page Chats, apps)
router = APIRouter()


@router.post("/api/chats/poll", dependencies=[Depends(assistant)])
async def api_make(request: Request, prof=Depends(chats._on)):
    """{"id": chat, "q": question, "opts": [answers], "multi": bool}"""
    b = await json_body(request, 8 * 1024)
    try:
        return {"item": await stellen(prof["id"], chats._cid(b.get("id")), b.get("q"), b.get("opts"), bool(b.get("multi")))}
    except (LookupError, PermissionError, ValueError, OverflowError) as e:
        raise chats._err(e)


@router.post("/api/chats/poll/vote", dependencies=[Depends(assistant)])
async def api_vote(request: Request, prof=Depends(chats._on)):
    """{"id": chat, "mid": message, "picks": [answer numbers]}"""
    b = await json_body(request, 1024)
    try:
        abstimmen(prof["id"], chats._cid(b.get("id")), chats._mid(b.get("mid")), b.get("picks"))
    except (LookupError, PermissionError, ValueError) as e:
        raise chats._err(e)
    return {"ok": True}


@router.post("/api/chats/poll/close", dependencies=[Depends(assistant)])
async def api_close(request: Request, prof=Depends(chats._on)):
    b = await json_body(request, 1024)
    try:
        return {"win": schliessen(prof["id"], chats._cid(b.get("id")), chats._mid(b.get("mid")))}
    except (LookupError, PermissionError, ValueError) as e:
        raise chats._err(e)
