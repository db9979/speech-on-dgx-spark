"""Steuerzentrale am Bildschirm (plan Raspberry-Pi split B9, Dominik 2026-10-16 "ja, super. so machen wir das").

One text screen on the HDMI output of the panel computer, without a graphical desktop: the program app/steuerzentrale.py runs
as the unit speech-spark-schirm on the first console (tty1), starts at boot without anyone signing in, and draws the
control centre once a second. This module is its panel half:

    GET /api/schirm/zustand   what the screen shows: the Live picture as the wall monitor sees it (live.snapshot
                              "monitor": kinds, places, times, never what was asked or answered), both computers
                              (rechnerblick), the warnings (health.alerts), the day in numbers (admin.glance), whether
                              the screen is on now and where the picture sits (Schutz vor Einbrennen, gehaeuse.versatz).
                              Only from this machine itself (loopback, no forwarded sender) and only with the screen's
                              key (KEY, made here, readable by the service user only), at most RATE schirm a minute.
    loop()                    every SCHAUEN_S: switch on Funktionen → Steuerzentrale and the unit runs (and starts at
                              boot), switch off and it stops, then the login prompt on tty1 starts again (anmeldung;
                              not the unit's ExecStopPost, that cancelled every restart). sudoers allows exactly these
                              three commands.

Admin switch chat.schirm (off), the settings under Einstellungen → System → Steuerzentrale: on from schirm_an to
schirm_aus o'clock (the same hour twice: always on), the font size (auto, kleiner, groesser). Logs: "schirm: …" with
fixed words and numbers.
"""
import hmac
import os
import secrets
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi import APIRouter, HTTPException, Request  # noqa: E402

import guard  # noqa: E402
from steuerzentrale import HEADER, KEY, PFAD  # noqa: E402,F401  (one place for the key's file, header and path)

UNIT = "speech-spark-schirm"
ZAHLEN = {"schirm_an": (7, 0, 23), "schirm_aus": (23, 0, 23)}
SCHRIFT = ("auto", "kleiner", "groesser")
SCHAUEN_S = 10          # how often the loop compares the switch with the unit
NOCHMAL_S = 300         # after a failed start or stop, the next try
SIEHT_S = 15            # a screen that asked within this many seconds counts as showing
GLANCE_S = 30           # the day in numbers is looked up again after this many seconds

_lock = threading.Lock()
_st = {"gesehen": 0.0, "fehler": 0.0, "glance": (0.0, {})}


def cfg_chat(c=None):
    import features
    return features.chat_cfg() if c is None else c


def admin_on(c=None):
    import features
    return features.admin_on("schirm", c)


def zahl(c, key):
    d, lo, hi = ZAHLEN[key]
    v = c.get(key, d)
    return v if isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi else d


def check(c):
    """None when the screen settings in chat are fine, else the reason (admin.validate)."""
    for k, (d, lo, hi) in ZAHLEN.items():
        v = c.get(k, d)
        if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
            return f"{k}: {lo} bis {hi}"
    if c.get("schirm_schrift", "auto") not in SCHRIFT:
        return "schirm_schrift: auto, kleiner oder groesser"
    return None


def an_jetzt(c, now=None):
    """Whether the screen shows now: from schirm_an to schirm_aus o'clock (both the same: always)."""
    import gehaeuse
    an, aus = zahl(c, "schirm_an"), zahl(c, "schirm_aus")
    return an == aus or gehaeuse.im_fenster(an, aus, now)


def schluessel(create=False):
    """The screen's key (only the service user reads it; the screen program reads it from the same file)."""
    try:
        with open(KEY) as f:
            k = f.read().strip()
        if len(k) >= 32:
            return k
    except OSError:
        pass
    if not create:
        return ""
    k = secrets.token_urlsafe(32)
    fd = os.open(KEY, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(k + "\n")
    print("schirm: schluessel neu", flush=True)
    return k


def sieht(now=None):
    """A screen asked within SIEHT_S seconds."""
    return (time.time() if now is None else now) - _st["gesehen"] < SIEHT_S


def _glance(now):
    t, d = _st["glance"]
    if now - t > GLANCE_S or not d:
        try:
            import admin
            from common import load_config
            g = admin.glance(load_config())
            d = {k: g.get(k) for k in ("version", "backup", "answers", "first_sound", "slower", "hours", "speakers")}
        except Exception as e:
            print("schirm: tageszahlen", type(e).__name__, flush=True)
            d = d or {}
        _st["glance"] = (now, d)
    return d


def _alerts(now):
    import health
    return [{k: x.get(k) for k in ("kind", "level", "text")} for x in health.alerts_cached(now)][:12]


def zustand(now=None, c=None):
    """What the screen shows (only kinds, places, times and numbers)."""
    import gehaeuse
    import live
    import rechnerblick
    now = time.time() if now is None else now
    c = cfg_chat(c)
    return {"t": round(now, 1), "an": an_jetzt(c, now), "versatz": list(gehaeuse.versatz(now)),
            "schrift": c.get("schirm_schrift", "auto") if c.get("schirm_schrift") in SCHRIFT else "auto",
            "zeiten": [zahl(c, "schirm_an"), zahl(c, "schirm_aus")], "live_an": live.on(),
            "live": live.snapshot("monitor", now), "rechner": rechnerblick.fuer_status(now),
            "tag": _glance(now), "hinweise": _alerts(now)}


def for_live(c=None, now=None):
    """Zustand → Live, box „Steuerzentrale“: on, showing, screen on by the times (no content)."""
    c = cfg_chat(c)
    if not admin_on(c):
        return {"on": False}
    return {"on": True, "sieht": sieht(now), "an": an_jetzt(c, now)}


def probes():
    """For the Dienst-Wächter: the screen, while the switch is on and the unit is installed (it asks once a second)."""
    from common import unit_exists
    if not admin_on() or not unit_exists(UNIT):
        return {}
    return {"schirm": {"schirm": True}}


# ---------------------------------------------------------------- the unit follows the switch
def _systemctl(*args):
    try:
        return subprocess.run(["sudo", "-n", "/usr/bin/systemctl", *args, UNIT], timeout=30,
                              capture_output=True).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def anmeldung():
    """The login prompt on tty1 again, after the screen stopped for good (sudoers: exactly this command)."""
    try:
        ok = subprocess.run(["sudo", "-n", "/usr/bin/systemctl", "start", "getty@tty1.service"], timeout=30,
                            capture_output=True).returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    print(f"schirm: anmeldung {'zurueck' if ok else 'fehler'}", flush=True)
    return ok


def abgleich(now=None, c=None):
    """One comparison: returns "an", "aus", "fehler" or "" (nothing to do)."""
    from common import run, unit_exists
    now = time.time() if now is None else now
    if now - _st["fehler"] < NOCHMAL_S or not unit_exists(UNIT):
        return ""
    soll = admin_on(cfg_chat(c))
    laeuft = run(["systemctl", "is-active", UNIT])[1].strip() in ("active", "activating")
    if soll == laeuft:
        return ""
    if soll:
        schluessel(create=True)
    ok = _systemctl("enable", "--now") if soll else _systemctl("disable", "--now")
    if not ok:
        _st["fehler"] = now
        print(f"schirm: dienst {'start' if soll else 'stopp'} fehler", flush=True)
        return "fehler"
    print(f"schirm: dienst {'an' if soll else 'aus'}", flush=True)
    if not soll:
        anmeldung()
    return "an" if soll else "aus"


async def loop():
    import asyncio
    while True:
        try:
            await asyncio.to_thread(abgleich)
        except Exception as e:
            print("schirm: abgleich", type(e).__name__, flush=True)
        await asyncio.sleep(SCHAUEN_S)


# ---------------------------------------------------------------- the route (only the screen on this machine)
router = APIRouter()


def _lokal(request):
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1") and not request.headers.get("x-forwarded-for") \
        and not request.headers.get("forwarded")


@router.get("/api/schirm/zustand", include_in_schema=False)
def schirm_zustand(request: Request):
    if not _lokal(request):
        print("schirm: abgelehnt nicht lokal", flush=True)
        raise HTTPException(404, "not found")
    guard.limit(request, "schirm")
    if not admin_on():
        print("schirm: abgelehnt aus", flush=True)
        raise HTTPException(404, "not found")
    k, got = schluessel(), request.headers.get(HEADER, "")
    if not k or len(got) > 80 or not hmac.compare_digest(k, got):
        print("schirm: abgelehnt schluessel", flush=True)
        raise HTTPException(401, "wrong key")
    now = time.time()
    with _lock:
        neu = not sieht(now)
        _st["gesehen"] = now
    if neu:
        print("schirm: verbunden", flush=True)
    return zustand(now)
