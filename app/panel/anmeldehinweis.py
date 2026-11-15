"""Hinweis bei neuer Anmeldung (Nextcloud-Ideen 11, Dominik 2026-11-15 „alles umsetzen“; Idee aus Nextclouds
„Suspicious Login“, nur als Idee, kein Code): meldet sich ein Profil mit PIN in einem Browser an, dessen Art (Gerät
und Browser, profiles.agent_label) unter seinen anderen Anmeldungen nicht vorkommt, bekommen seine Geräte eine
Mitteilung „Neue Anmeldung: Windows · Firefox“ mit dem Weg zu Ich → Sicherheit, wo „Abmelden“ genau diese Anmeldung
beendet.

Feste Regeln, nie ein Modell:
- nur mit dem Admin-Schalter chat.login_notice (aus) und nicht für ein gesperrtes Profil (features.allowed);
- die allererste Anmeldung eines Profils meldet nichts (es gibt nichts zum Vergleichen);
- dieselbe Art wie eine noch gültige andere Anmeldung meldet nichts; nur die Art zählt, nie die Adresse;
- höchstens MAX_DAY Hinweise je Profil und Tag (DayCounter), damit niemand die Geräte zuschüttet.
Nichts wird gespeichert: verglichen wird mit profiles.sessions. In die Mitteilung kommt nur die kurze Art.
Journal: „anmeldehinweis: gesendet n geraete | <Profil>“, „anmeldehinweis: kein hinweis <grund> | <Profil>“.

The bottom layer (test_schichten.GRUND): it imports no panel module; the login hands in what it needs (Teile: the
profile's sessions, whether the function is allowed, the log name and push.send).
"""
import asyncio
from typing import NamedTuple

from common import DayCounter


class Teile(NamedTuple):
    sessions: object      # uid -> profiles.sessions(uid)
    allowed: object       # uid -> features.allowed("anmeldehinweis", uid)
    who: object           # uid -> profiles.log_name(profile)
    send: object          # push.send

MAX_DAY = 5               # notes per profile and day
TAG = "login"             # push.WHY
_count = DayCounter(gesendet=0)   # today: notes sent, and per profile under "u:<id>"
_tasks = set()            # running notes, kept so they are not collected early


def neu(uid, raw, mine):
    """The short kind of browser ("Windows · Firefox") of the login `raw` (the cookie value) when it is new for the
    profile, else ""; also "" for the profile's first login and for a login that is not (or no longer) there.
    mine: the profile's sessions (profiles.sessions)."""
    parts = str(raw or "").split(".")
    sid = parts[2] if len(parts) == 4 else ""
    this = next((x for x in mine if x["id"] == sid), None)
    others = [x for x in mine if x["id"] != sid]
    if not this or not others or any(x["agent"] == this["agent"] for x in others):
        return ""
    return this["agent"]


def _why(uid, raw, t):
    """(reason word, kind): the fixed reason why there is no note, or ("", kind)."""
    if not t.allowed(uid):
        return "aus", ""
    kind = neu(uid, raw, t.sessions(uid))
    if not kind:
        return "bekannt", ""
    if _count.today().get("u:" + uid, 0) >= MAX_DAY:
        return "genug", ""
    return "", kind


async def melden(uid, raw, t):
    """Sends the note when one is due; returns the number of devices reached (0 without a note)."""
    who = t.who(uid)
    why, kind = _why(uid, raw, t)
    if why:
        print(f"anmeldehinweis: kein hinweis {why} | {who}", flush=True)
        return 0
    _count.bump("u:" + uid)
    try:
        n = await t.send(uid, "Neue Anmeldung", f"{kind}. Warst du das nicht? Ich → Sicherheit → Abmelden.",
                            tag=TAG, to="every", why="Anmeldung")
    except Exception as e:   # a note that could not go never stops the login
        print(f"anmeldehinweis: nicht gesendet {type(e).__name__} | {who}", flush=True)
        return 0
    _count.bump("gesendet")
    print(f"anmeldehinweis: gesendet {n} geraete | {who}", flush=True)
    return n


def ask(uid, raw, teile):
    """From the login (account.profile_login): the check and the note in the background, never waiting."""
    try:
        task = asyncio.get_running_loop().create_task(melden(uid, raw, teile))
    except RuntimeError:
        return False
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return True


def heute():
    """Live: notes sent today, a number only."""
    return _count.counts().get("gesendet", 0)
