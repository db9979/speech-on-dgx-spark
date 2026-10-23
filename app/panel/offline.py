"""Ohne Internet (Dominik 2026-10-23: „sind wir komplett offline fähig … dass das System und der Assistent im Netz
weiterhin komplett funktioniert“): what the Spark needs to keep running in the home network alone, looked at on demand.

Zustand → Überblick → „Ohne Internet“ → „Jetzt prüfen“ (POST /api/admin/offline/check, admin, rate limit "offline")
looks once, only reading, at:
- Sprachmodell, Hören, Sprechen: do they answer (dienstwacht.probe, like the Dienst-Wächter). They load only from their
  own disk: the engines with HF_HUB_OFFLINE (engine.sh, modelle.py's Docker recipe, the Notbetrieb unit), the speech
  servers after modelle.ohne_netz(); test_offline keeps every loader so;
- the clocks: this computer's (common.uhr: set by a time server?), the time server in the home network
  (watch.zeitserver, one SNTP question to UDP 123 after netguard.resolve at the home level, nothing else is sent) and,
  when the models run on another computer, its clock against this one (steuer.uhr_vergleich): its Wärter takes a
  request only within tarswart.WINDOW seconds, so two clocks drifting apart without the internet stop every command;
- the names the Spark is reached by from outside (chat.verbund_domain and the name this page was opened with): do
  they point into the home network? Without the internet a name that points out is not found, and the apps lose the
  Spark unless the router knows the name (a local DNS entry);
- what pauses without the internet (dienstwacht: watched services on public addresses, functions that need it).

The answer carries fixed words, numbers and the Spark's own names; the journal one line "offline: pruefung" with the
counts. alerts() puts a hint on top of the admin pages while the model computer refuses because of the time, which
otherwise looks as if it were gone (Notbetrieb).

watch.zeitserver: one private IPv4 address (the FRITZ!Box: Heimnetz → Netzwerk → Zeitsynchronisation). install.sh
writes it for systemd-timesyncd or chrony on each computer, with the usual servers behind it; the model computer gets
it with the speech settings (common.SYNC_SECTIONS "watch"). Checked the same way here, in admin.py and in install.sh.
"""
import asyncio
import ipaddress
import re
import socket
import struct
import time

from fastapi import APIRouter, Depends, Request

import dienstwacht
import features
import guard
import netguard
import steuer
from common import load_config, model_local, uhr
from core import auth

router = APIRouter()

NTP_PORT, NTP_WAIT = 123, 1.5   # one SNTP question, this long for the answer
NTP_1970 = 2208988800           # seconds from 1900 (NTP) to 1970
UHR_OK = 2.0                    # two clocks this close count as the same
UHR_WARN = 30.0                 # from here on the Wärter's window (60 s) comes close
NAME_WAIT = 3.0                 # a name lookup may take this long without the internet
NAME = re.compile(r"(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
MODELS = ("qwen", "asr", "tts")


def zeitserver(v):
    """The time server's address when v is one (a private IPv4 address, not loopback or link-local), else ""."""
    v = str(v or "").strip()
    if not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", v):
        return ""
    try:
        ip = ipaddress.IPv4Address(v)
    except ValueError:
        return ""
    return v if ip.is_private and not (ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast) else ""


def sntp_answer(data, t0, t1):
    """(seconds the server is ahead of this clock, round trip ms) from a 48-byte SNTP answer, None when the server
    has no time of its own (leap indicator 3, stratum 0) or the answer is not one."""
    if len(data) < 48 or data[0] >> 6 == 3 or data[1] == 0 or data[0] & 7 not in (4, 5):
        return None
    secs, frac = struct.unpack("!II", data[40:48])
    if not secs:
        return None
    server = secs - NTP_1970 + frac / 2 ** 32
    return round(server - (t0 + t1) / 2, 1), max(0, int((t1 - t0) * 1000))


def sntp(host, wait=NTP_WAIT):
    """One SNTP question (RFC 4330, client mode) to the time server, after netguard checked its address at the home
    level. (ahead seconds, ms) or None when it does not answer in time."""
    token = netguard.QUIET.set(True)   # a check is no request: not on the Wächter list, no Selbst-Notaus
    try:
        ip = netguard.resolve(host, NTP_PORT, netguard.HOME)
    except Exception:   # noqa: BLE001 - Blocked, or httpx.ConnectError when the name is not found
        return None
    finally:
        netguard.QUIET.reset(token)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(wait)
        try:
            t0 = time.time()
            s.sendto(b"\x1b" + 47 * b"\0", (ip, NTP_PORT))
            while True:
                data, src = s.recvfrom(512)
                if src[0] == ip:
                    break
            t1 = time.time()
        except OSError:
            return None
    return sntp_answer(data, t0, t1)


def _names(request, cfg):
    """The Spark's names from outside: the own address for other Sparks and the name this page came through."""
    out = []
    own = str((cfg.get("chat") or {}).get("verbund_domain") or "").strip().lower()
    for h in (own, request.headers.get("x-forwarded-host", "").split(",")[0], request.headers.get("host", "")):
        h = h.strip().lower().rsplit(":", 1)[0] if h.count(":") <= 1 else ""
        if NAME.fullmatch(h) and not h.endswith((".local", ".localhost")) and h not in out:
            out.append(h)
    return out[:3]


def _where(host):
    """'lan' when every address of the name is in the home network, 'net' when one points out, '' when not found."""
    try:
        ips = {ipaddress.ip_address(a[4][0].split("%")[0]) for a in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    except (OSError, ValueError, UnicodeError):
        return ""
    return "net" if any(ip.is_global for ip in ips) else ("lan" if ips else "")


def _row(rid, level, de, en, way=""):
    return {"id": rid, "level": level, "de": de, "en": en, "way": way}


def _ab(s):
    return f"{abs(s):.0f} s" if abs(s) >= 10 else f"{abs(s):.1f} s"


def uhr_rows(cfg, hier=None, server=None, modell=None):
    """The clock rows from what was measured (kept apart for the tests: no time of day, no network)."""
    rows = []
    hier = uhr() if hier is None else hier
    if hier.get("ntp") is True:
        rows.append(_row("uhr", "ok", "Uhr des Panel-Rechners: von einem Zeitserver gestellt.",
                         "Clock of the panel computer: set by a time server."))
    elif hier.get("ntp") is False:
        rows.append(_row("uhr", "warn", "Uhr des Panel-Rechners: gerade von keinem Zeitserver gestellt, sie läuft frei.",
                         "Clock of the panel computer: not set by a time server right now, it runs freely."))
    zs = zeitserver((cfg.get("watch") or {}).get("zeitserver"))
    if not zs:
        rows.append(_row("zeitserver", "warn", "Kein Zeitserver im Heimnetz eingetragen: ohne Internet stellt niemand die Uhren.",
                         "No time server in the home network set: without the internet nobody sets the clocks.", "zeit"))
    elif server is None:
        rows.append(_row("zeitserver", "bad", f"Zeitserver im Heimnetz ({zs}) antwortet nicht.",
                         f"Time server in the home network ({zs}) does not answer.", "zeit"))
    else:
        ab, ms = server
        lvl = "ok" if abs(ab) < UHR_OK else "warn"
        rows.append(_row("zeitserver", lvl, f"Zeitserver im Heimnetz ({zs}) antwortet in {ms} ms, Abstand zur Uhr hier {_ab(ab)}.",
                         f"Time server in the home network ({zs}) answers in {ms} ms, {_ab(ab)} from the clock here.", "zeit"))
    if model_local(cfg):
        return rows
    if modell is None:
        rows.append(_row("modelluhr", "warn", "Uhr des Modell-Rechners: nicht gelesen (antwortet nicht oder ältere Version).",
                         "Clock of the model computer: not read (no answer or an older version).", "modelle"))
    elif modell.get("abgelehnt"):
        rows.append(_row("modelluhr", "bad", "Uhr des Modell-Rechners weicht über 60 s ab: er nimmt keine Befehle vom Panel an.",
                         "Clock of the model computer is more than 60 s off: it takes no commands from the panel.", "zeit"))
    else:
        ab = modell["ab"]
        lvl = "ok" if abs(ab) < UHR_OK else ("warn" if abs(ab) < UHR_WARN else "bad")
        ntp = {True: ("von einem Zeitserver gestellt", "set by a time server"),
               False: ("läuft frei", "runs freely"), None: ("", "")}[modell.get("ntp")]
        rows.append(_row("modelluhr", lvl,
                         f"Uhr des Modell-Rechners: {_ab(ab)} {'vor' if ab >= 0 else 'nach'}" + (f", {ntp[0]}." if ntp[0] else "."),
                         f"Clock of the model computer: {_ab(ab)} {'ahead' if ab >= 0 else 'behind'}" + (f", {ntp[1]}." if ntp[1] else "."),
                         "zeit"))
    return rows


async def _models(cfg):
    rows = []
    act = dienstwacht.active(cfg=cfg)
    for sid in MODELS:
        if sid not in act:
            continue
        key, p = next(iter(act[sid].items()))
        try:
            ok = (await dienstwacht.probe(sid, key, p, cfg)).ok
        except Exception:   # noqa: BLE001 - a check never fails because of one service
            ok = False
        de, en = dienstwacht.SVC[sid][:2]
        rows.append(_row(sid, "ok" if ok else "bad",
                         f"{de}: antwortet, lädt nur aus dem eigenen Speicher." if ok else f"{de}: antwortet nicht.",
                         f"{en}: answers, loads only from its own disk." if ok else f"{en}: does not answer.", "modelle"))
    return rows, act


async def _paused(cfg, act):
    """What needs the internet: watched services on public addresses and switched-on functions that need it."""
    c = cfg.get("chat") or {}
    names = []
    for sid, parts in act.items():
        if sid in MODELS or sid == "inet" or sid not in dienstwacht.SVC:
            continue
        for key, p in parts.items():
            host = dienstwacht._host(sid, p)
            if host and await asyncio.to_thread(dienstwacht._is_public, host) and dienstwacht.SVC[sid][:2] not in names:
                names.append(dienstwacht.SVC[sid][:2])
    for key, de in dienstwacht.NEEDS_NET:
        try:
            on = features.admin_on(key, c)
        except KeyError:
            on = False
        f = features.BY_KEY.get(key)
        name = (f.de, f.en) if f else (de, de)
        if on and name[0] not in [n[0] for n in names] and not (key == "search" and "web" in act):
            names.append(name)
    if not names:
        return [_row("pause", "info", "Nichts Eingeschaltetes braucht das Internet.", "Nothing switched on needs the internet.", "dienste")]
    return [_row("pause", "info", "Ohne Internet pausiert: " + ", ".join(n[0] for n in names) + ". Alles andere läuft im Heimnetz weiter.",
                 "Paused without the internet: " + ", ".join(n[1] for n in names) + ". Everything else keeps running at home.",
                 "dienste")]


async def _addresses(request, cfg):
    rows = []
    for h in _names(request, cfg):
        try:
            where = await asyncio.wait_for(asyncio.to_thread(_where, h), NAME_WAIT)
        except asyncio.TimeoutError:
            where = ""
        if where == "lan":
            rows.append(_row("name", "ok", f"{h}: zeigt ins Heimnetz, Apps finden den Spark auch ohne Internet.",
                             f"{h}: points into the home network, apps find the Spark without the internet too."))
        elif where == "net":
            rows.append(_row("name", "warn", f"{h}: zeigt ins Internet. Ohne Internet finden Apps den Spark unter diesem Namen nicht; "
                                             "ein lokaler DNS-Eintrag im Router hilft.",
                             f"{h}: points to the internet. Without the internet apps do not find the Spark by this name; "
                             "a local DNS entry in the router helps."))
        else:
            rows.append(_row("name", "bad", f"{h}: wird gerade nicht gefunden.", f"{h}: is not found right now."))
    if not rows:
        rows.append(_row("name", "info", "Der Spark ist nur über Adressen im Heimnetz geöffnet: nichts zu prüfen.",
                         "The Spark was opened only by addresses in the home network: nothing to check."))
    return rows


async def check(request, cfg=None):
    """All rows, the counts and the time it took; one journal line."""
    cfg = load_config() if cfg is None else cfg
    t0 = time.monotonic()
    zs = zeitserver((cfg.get("watch") or {}).get("zeitserver"))
    server_task = asyncio.to_thread(sntp, zs) if zs else asyncio.sleep(0, None)
    modell_task = asyncio.to_thread(steuer.uhr_vergleich, cfg) if not model_local(cfg) else asyncio.sleep(0, None)
    (models, act), server, modell, names = await asyncio.gather(_models(cfg), server_task, modell_task, _addresses(request, cfg))
    rows = models + uhr_rows(cfg, server=server, modell=modell) + names + await _paused(cfg, act)
    count = {k: sum(r["level"] == k for r in rows) for k in ("ok", "warn", "bad")}
    ms = int((time.monotonic() - t0) * 1000)
    print(f"offline: pruefung | {count['ok']} ok {count['warn']} warnung {count['bad']} fehler | {ms} ms", flush=True)
    return {"rows": rows, "count": count, "ms": ms, "t": int(time.time())}


@router.post("/api/admin/offline/check", dependencies=[Depends(auth)])
async def admin_check(request: Request):
    """Zustand → Überblick → Ohne Internet → „Jetzt prüfen“."""
    guard.limit(request, "offline", admin=True)
    return await check(request)


def alerts(now=None):
    """A hint on top of the admin pages while the model computer refuses because of the time (steuer.uhr_abgelehnt)."""
    if not steuer.uhr_abgelehnt(now):
        return []
    return [{"kind": "uhr", "level": "bad", "go": "Einstellungen → Spark → Betrieb → Zeitserver im Heimnetz",
             "text": "Die Uhren von Panel- und Modell-Rechner gehen über 60 Sekunden auseinander: der Modell-Rechner nimmt "
                     "keine Befehle an und wirkt wie weg. Abhilfe: ein Zeitserver im Heimnetz für beide Rechner."}]
