"""Entwickeln auf dem Pi (plan plaene/opencode-pi.md, Dominik 2026-11-03, Paket 1): the panel's side of app/entwickeln.py,
for admins only, default off (admin switch chat.entwickeln).

OpenCode runs in the terminal of the panel computer as the user spark-dev in its own clone; its changes are commits
on the branch „lokal“ there (Weg B, no GitHub). The panel never reads that clone and never runs any of it: root
(update.sh with app/entwickeln.py) takes the commits, checks them, runs the quick test in a sandbox and installs
them like an update. Here only:

    for_live / live_sub   Zustand → Live, box „Entwickeln“: lokale Änderungen N, waiting in the clone, the last result
    alerts                a hint on top of the admin pages while an update or an install kept the running version
                          because of the local changes (conflict, red quick test), with the way to the update log
    GET  /api/admin/entwickeln             the copy root wrote (counts, short commits, fixed words, red test names)
    POST /api/admin/entwickeln/einspielen  „Lokal einspielen“: a new version of the Spark, so the code every time
    POST /api/admin/entwickeln/zurueck     back to what ran before the last local install (same version only)
    POST /api/admin/entwickeln/verwerfen   the installed version without the local commits (they stay in the clone)

The three POSTs only write the wish STATE/update-lokal (one fixed word) and start the update unit through
update.begin (backup first, the lock, the progress bar); update.sh checks the wish and every rule again as root.

Weg A (package 2, switch Funktionen → Entwickeln auf dem Pi → An GitHub geben, chat.entwickeln_github, off):
    POST /api/admin/entwickeln/github  {"thema"}: a fresh code; the topic in the fixed charset (entwickeln.thema_pruefen)
                          is the wish STATE/github-wunsch, then root's oneshot speech-spark-github pushes spark-dev's
                          branch as opencode/<thema> with root's deploy key (never main, never forced; offline it
                          waits and the timer tries again). The panel never sees the key.
    GET  /api/admin/entwickeln/github  the branches handed over, GitHub's "Tests" for each (the public API through
                          update.green_runs, no key; at most every TESTS_S per branch), the fixed hint for Dominik.
Package 3: the page Zustand → Werkstatt → Entwickeln (static/js/entwickeln.js: tiles, local commits with their
titles, branches on GitHub, the buttons, the Ablauf) and its terminal as spark-dev (below, own sub-switch); the
command line sudo speech-spark lokal einspielen|zurueck|verwerfen|status keeps working beside it.
Logs: "entwickeln: …" with fixed words only.
"""
import asyncio
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import core  # noqa: E402
import entwickeln  # noqa: E402
import features  # noqa: E402
import guard  # noqa: E402
import notaus  # noqa: E402
from core import admin_code, admin_code_fresh, auth  # noqa: E402

MAX_BODY = 256           # the POSTs carry nothing
MAX_BODY_GH = 512        # {"thema": …}: the topic is cut to 200 characters and its fixed charset anyway
TESTS_S = 300            # GitHub's tests of one branch asked at most this often (60 questions an hour for everything)
TESTS_ZWEIGE = 3         # only the newest branches are asked about
HINWEIS_S = 3 * 86400    # a refused update or install stays on top of the admin pages this long (or until the next ok)
WEG = "Zustand → Werkstatt → Entwickeln"   # the page of package 3: every hint points there (a jump link); "go" in an alert is written out (test_sprunglinks reads it as a literal)
ART_TEXT = {"einspielen": ("Lokal einspielen", "Install local changes"), "zurueck": ("Lokal zurück", "Local back"),
            "verwerfen": ("Lokal verwerfen", "Drop local changes"), "aufsetzen": ("Update mit lokalen Änderungen", "Update with local changes")}


def _an(cfg=None):
    """Funktionen → Entwickeln auf dem Pi (cfg: the whole configuration, None reads it)."""
    return features.admin_on("entwickeln", None if cfg is None else cfg.get("chat", {}))


def _github_an(cfg=None):
    """Funktionen → Entwickeln auf dem Pi → An GitHub geben (needs Entwickeln auf dem Pi, features.parent)."""
    return features.admin_on("entwickelngithub", None if cfg is None else cfg.get("chat", {}))


def github_daten(path=None):
    """What root last wrote about Weg A (entwickeln.github_anzeige_lesen: checked again here)."""
    return entwickeln.github_anzeige_lesen(path)


def daten(path=None):
    """What root last wrote (entwickeln.anzeige_lesen: checked again here)."""
    return entwickeln.anzeige_lesen(path)


def for_live(path=None, gh_path=None):
    """Zustand → Live, box „Entwickeln“: counts and fixed words only, never a commit text, a path or a test output."""
    if not _an():
        return {"on": False}
    d = daten(path)
    out = {"on": True, "anzahl": d.get("anzahl", 0), "offen": d.get("offen"),
           "letzter": (d.get("letzter") or {}).get("ergebnis"), "art": (d.get("letzter") or {}).get("art")}
    if _github_an():
        g = github_daten(gh_path)
        out.update(github=(g.get("letzter") or {}).get("zustand"), gegeben=len(g["zweige"]))
    if _terminal_an():
        out["terminal"] = len(TERM)
    import codeauftrag
    if codeauftrag.an():
        liste = codeauftrag.auftraege()
        out["auftraege"] = sum(1 for x in liste if x["zustand"] == "fertig")
        out["auftrag_laeuft"] = codeauftrag.laeuft(liste)
    return out


def live_sub(v):
    teile = [f"lokale Änderungen: {v.get('anzahl', 0)}"]
    if v.get("offen"):
        teile.append(f"{v['offen']} im Klon noch nicht eingespielt")
    if v.get("letzter") and v["letzter"] != "ok" and v.get("art") in ART_TEXT:
        teile.append(f"zuletzt {ART_TEXT[v['art']][0]} abgelehnt: {v['letzter']}")
    if v.get("gegeben"):
        teile.append(f"an GitHub gegeben: {v['gegeben']}")
    if v.get("github") and v["github"] != "gegeben":
        teile.append(f"an GitHub zuletzt: {v['github']}")
    if v.get("terminal"):
        teile.append(f"Terminal offen: {v['terminal']}")
    if v.get("auftrag_laeuft"):
        teile.append("Code-Auftrag läuft")
    if v.get("auftraege"):
        teile.append(f"Code-Aufträge fertig: {v['auftraege']}")
    return " · ".join(teile)


def alerts(now=None, path=None, gh_path=None):
    """While the last update or install was refused because of the local changes (the running version stayed);
    with An GitHub geben the hint after a branch went to GitHub, or why it did not go (waiting says nothing)."""
    if not _an():
        return []
    out = []
    lz = daten(path).get("letzter") or {}
    now = time.time() if now is None else now
    if lz.get("ergebnis") not in (None, "ok", "leer") and now - lz.get("t", 0) <= HINWEIS_S:
        text = entwickeln.GRUENDE.get(lz["ergebnis"], entwickeln.GRUENDE["fehler"])[0]
        out.append({"kind": "entwickeln", "level": "warn", "go": "Zustand → Werkstatt → Entwickeln",
                    "text": f"{ART_TEXT[lz['art']][0]}: {text}" + (f" (rot: {', '.join(lz['rot'][:5])})" if lz.get("rot") else "")
                    + f". Weiter unter {WEG}."})
    if _github_an():
        g = github_daten(gh_path)
        gl = g.get("letzter") or {}
        if gl.get("zustand") and gl["zustand"] != "wartet" and now - gl.get("t", 0) <= HINWEIS_S:
            if gl["zustand"] == "gegeben" and g["zweige"]:
                out.append({"kind": "entwickeln_github", "level": "info", "go": "Zustand → Werkstatt → Entwickeln",
                            "text": entwickeln.hinweis(g["zweige"][0]["zweig"], _repo())[0]})
            elif gl["zustand"] != "gegeben":
                out.append({"kind": "entwickeln_github", "level": "warn", "go": "Zustand → Werkstatt → Entwickeln",
                            "text": "An GitHub geben: " + entwickeln.GH_GRUENDE[gl["zustand"]][0]
                            + f". Weiter unter {WEG}."})
    return out


def _repo():
    """"owner/repo" of the installed version's GitHub remote, "" for a clone from elsewhere."""
    import update
    return update.github_repo(update.installed_version().get("remote")) or ""


router = APIRouter()


@router.get("/api/admin/entwickeln", dependencies=[Depends(auth)])
async def admin_entwickeln(request: Request):
    """The state of the local changes for an admin (counts, short commits, fixed words, red test names)."""
    guard.limit(request, "entwickeln", None, True)
    import update
    return {"an": _an(), **await asyncio.to_thread(daten), "update": await asyncio.to_thread(update.update_running),
            **await asyncio.to_thread(seite)}


def seite(cfg=None):
    """What Zustand → Werkstatt → Entwickeln shows beside the copy: the running version, the internet (the Dienst-
    Wächter's probe, "unbekannt" without it), the sub-switches, OpenCode there or not, the terminal's numbers."""
    import common
    import dienstwacht
    from common import load_config
    cfg = load_config() if cfg is None else cfg
    v = common.installed_version()
    ver = str(v.get("version") or "")
    if not re.fullmatch(r"V?[0-9][0-9.]{0,20}(\+lokal)?", ver):
        ver = ""
    if not dienstwacht.admin_on(cfg.get("chat", {})):
        netz = "unbekannt"
    else:
        netz = "weg" if dienstwacht.down("inet") else "da"
    import codeauftrag
    return {"version": ver, "internet": netz, "github_an": _github_an(cfg), "terminal_an": _terminal_an(cfg),
            "auftrag_an": codeauftrag.an(cfg.get("chat", {})),
            "opencode": os.access(entwickeln.OPENCODE, os.X_OK), "opencode_version": entwickeln.werkstatt.OPENCODE_VERSION,
            "zweig": entwickeln.ZWEIG, "terminal": terminal_zahlen(), "leerlauf_min": LEERLAUF_S // 60}


async def _wunsch(request, art):
    guard.limit(request, "entwickeln_einspielen", None, True)
    await core.json_body(request, MAX_BODY, lenient=True)
    if not _an():
        print(f"entwickeln: {art} abgelehnt aus", flush=True)
        raise HTTPException(409, entwickeln.GRUENDE["aus"][0])
    import update
    if await asyncio.to_thread(update.update_running):
        print(f"entwickeln: {art} abgelehnt laeuft", flush=True)
        raise HTTPException(409, "Ein Update läuft schon.")
    with open(entwickeln.WUNSCH, "w") as f:
        f.write(art)
    try:
        out = await asyncio.to_thread(update.begin, "before-update", "")
    except HTTPException:
        try:
            os.remove(entwickeln.WUNSCH)
        except OSError:
            pass
        print(f"entwickeln: {art} abgelehnt start", flush=True)
        raise
    print(f"entwickeln: {art} gestartet", flush=True)
    guard.log("entwickeln_lokal", detail=ART_TEXT[art][0])
    return out


@router.post("/api/admin/entwickeln/einspielen", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_einspielen(request: Request):
    """„Lokal einspielen“: spark-dev's branch, checked and quick-tested by root, installed like an update."""
    return await _wunsch(request, "einspielen")


@router.post("/api/admin/entwickeln/zurueck", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_zurueck(request: Request):
    """Back to what ran before the last local install."""
    return await _wunsch(request, "zurueck")


@router.post("/api/admin/entwickeln/verwerfen", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_verwerfen(request: Request):
    """The installed version without the local commits (they stay in spark-dev's clone)."""
    return await _wunsch(request, "verwerfen")


_tests = {}   # branch -> (time, head, state): GitHub's "Tests" asked at most every TESTS_S


async def _tests_von(repo, zweig, kopf, now=None):
    import update
    now = time.time() if now is None else now
    c = _tests.get(zweig)
    if c and c[1] == kopf and now - c[0] < TESTS_S:
        return c[2]
    try:
        stand = entwickeln.tests_zustand(await update.green_runs(repo, zweig), zweig, kopf)
    except Exception as e:   # GitHub's limit, no internet, a broken answer: "unbekannt", asked again later
        print(f"entwickeln: github tests unbekannt {type(e).__name__}", flush=True)
        stand = "unbekannt"
    _tests[zweig] = (now, kopf, stand)
    return stand


@router.get("/api/admin/entwickeln/github", dependencies=[Depends(auth)])
async def admin_github_stand(request: Request):
    """Weg A for an admin: the branches handed to GitHub with their tests and links, the last state (fixed word),
    whether one waits for the internet, and the fixed hint for Dominik."""
    guard.limit(request, "entwickeln", None, True)
    g = await asyncio.to_thread(github_daten)
    repo = await asyncio.to_thread(_repo)
    zweige = []
    for i, z in enumerate(g["zweige"]):
        tests = await _tests_von(repo, z["zweig"], z["kopf"]) if repo and i < TESTS_ZWEIGE else "unbekannt"
        zweige.append({"zweig": z["zweig"], "kopf": z["kopf"][:7], "anzahl": z["anzahl"], "t": z["t"], "tests": tests,
                       "link": f"https://github.com/{repo}/tree/{z['zweig']}" if repo else ""})
    lz = g.get("letzter")
    return {"an": _github_an(), "zweige": zweige, "wartet": os.path.exists(entwickeln.GH_WUNSCH),
            "letzter": dict(lz, text=entwickeln.GH_GRUENDE[lz["zustand"]]) if lz else None,
            "hinweis": entwickeln.hinweis(zweige[0]["zweig"], repo) if zweige else None}


@router.post("/api/admin/entwickeln/github", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_github(request: Request):
    """„An GitHub geben“: the topic as the wish, then root's oneshot; the branch reaches GitHub only as
    opencode/<thema>, and only root's deploy key pushes it. A fresh code every time: it leaves the house."""
    guard.limit(request, "entwickeln_github", None, True)
    body = await core.json_body(request, MAX_BODY_GH, lenient=True)
    if not _github_an():
        print("entwickeln: github abgelehnt aus", flush=True)
        raise HTTPException(409, entwickeln.GH_GRUENDE["aus"][0])
    thema = entwickeln.thema_pruefen(body.get("thema") or entwickeln.ZWEIG)
    if not thema:
        print("entwickeln: github abgelehnt thema", flush=True)
        raise HTTPException(400, entwickeln.GH_GRUENDE["thema"][0])
    with open(entwickeln.GH_WUNSCH, "w") as f:
        f.write(thema)
    from core import run
    code, _out = await asyncio.to_thread(run, ["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", entwickeln.GH_UNIT], timeout=20)
    if code != 0:
        try:
            os.remove(entwickeln.GH_WUNSCH)
        except OSError:
            pass
        print("entwickeln: github abgelehnt start", flush=True)
        raise HTTPException(500, "An GitHub geben konnte nicht starten (sudo ./install.sh --entwickeln einmal neu)")
    zweig = entwickeln.GH_PREFIX + thema
    print("entwickeln: github gestartet", flush=True)
    guard.log("entwickeln_github", detail=zweig)
    return {"gestartet": True, "zweig": zweig, "hinweis": entwickeln.hinweis(zweig, await asyncio.to_thread(_repo))}


# ---------------------------------------------------------------- package 3: the terminal in the browser
# Zustand → Werkstatt → Entwickeln → Terminal (switch Funktionen → Entwickeln auf dem Pi → Terminal im Browser,
# chat.entwickeln_terminal, off): a shell as spark-dev, where `spark-opencode` starts OpenCode. Only an admin in the
# browser with a second sign-in step; every session asks a fresh code or passkey (stufen.LIST) and gets a ticket that
# opens the WebSocket once, within TICKET_S, in the same login. The panel starts root's fixed program
# entwickeln.TERM_WRAPPER (no arguments, one sudoers line): bash runs as spark-dev in a unit of its own, never as the
# panel's user and never as root. Ends: the window closes, „Sitzung beenden“, LEERLAUF_S without a key or output,
# SITZUNG_S, the switches off, the Notaus, logging out. The journal and Live count sessions; nothing that ran or
# showed is ever kept or logged.
TICKET_S = 30            # a ticket opens the terminal this long, once
TERM_MAX = 1             # spark-dev terminals from the panel at once
LEERLAUF_S = 3600        # no key and no output this long: the session ends
SITZUNG_S = 8 * 3600     # the longest session (entwickeln.TERM_GRENZE_S ends the unit at the same time)
MAX_MSG = 64 * 1024      # bytes per WebSocket message, both ways
MAX_BODY_TERM = 512      # {"cols", "rows"}
LESEN = 32 * 1024        # bytes read from the terminal at once
BEFEHL = ["setsid", "-c", "sudo", "-n", entwickeln.TERM_WRAPPER]   # the selftests put a harmless program here
TERM_TICKETS = {}        # sha256(ticket) -> {"login", "until", "cols", "rows", "who"}
TERM = {}                # id -> Terminal
TERM_STATS = {"heute": "", "sitzungen": 0, "abgewiesen": 0}


def _terminal_an(cfg=None):
    """Funktionen → Entwickeln auf dem Pi → Terminal im Browser (needs Entwickeln auf dem Pi, features.parent)."""
    return features.admin_on("entwickelnterminal", None if cfg is None else cfg.get("chat", {}))


def _log_terminal(word, n=1):
    print(f"entwickeln: terminal {word} {n}", flush=True)


def _notaus():
    """The Notaus at any stage from „aussen“ holds the terminal off, like the Fernzugang's shells (a refused start
    counts with notaus.refuse where it is logged)."""
    return notaus.level() >= notaus.STAGE["aussen"]


def _size(cols, rows):
    c = cols if isinstance(cols, int) and not isinstance(cols, bool) and 20 <= cols <= 400 else 80
    r = rows if isinstance(rows, int) and not isinstance(rows, bool) and 5 <= rows <= 200 else 24
    return c, r


def _winsize(fd, cols, rows):
    import fcntl
    import struct
    import termios
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


class Terminal:
    """One shell as spark-dev behind a pseudo terminal: the browser's keys in, its output out, nothing kept."""

    def __init__(self, login, who, cols, rows):
        self.id = secrets.token_hex(8)
        self.login, self.who, self.seit = login, who, time.time()
        self.zuletzt = self.seit
        self.ende = asyncio.Event()
        self.grund = ""
        self.proc = None
        self.fd = -1
        self.ws = None
        self.loop = None
        self.cols, self.rows = cols, rows

    def starten(self):
        """The program behind the terminal (entwickeln.TERM_WRAPPER through sudo, its own session and terminal)."""
        master, slave = os.openpty()
        try:
            _winsize(master, self.cols, self.rows)
            self.proc = subprocess.Popen(BEFEHL, stdin=slave, stdout=slave, stderr=slave, close_fds=True,
                                         env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C.UTF-8",
                                              "TERM": "xterm-256color"})
        except OSError:
            os.close(master)
            raise
        finally:
            os.close(slave)
        self.fd = master

    def lesen(self, q):
        """In a thread: the terminal's output to the window (a full queue slows the program, nothing piles up)."""
        while True:
            try:
                b = os.read(self.fd, LESEN)
            except OSError:
                b = b""
            try:
                fut = asyncio.run_coroutine_threadsafe(q.put(b or None), self.loop)
                fut.result(300)    # the window reads slowly: wait; gone (the session ended): stop
            except Exception:
                return
            if not b:
                return

    async def zum_fenster(self, q):
        while True:
            b = await q.get()
            if b is None:
                await self.end(self.grund or "beendet")
                return
            self.zuletzt = time.time()
            with contextlib.suppress(Exception):
                await self.ws.send_bytes(b)

    async def wache(self):
        """Idle and the longest session; the switches and the Notaus are checked with every key, too."""
        while not self.ende.is_set():
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.ende.wait(), 30)
            now = time.time()
            if now - self.zuletzt >= LEERLAUF_S:
                await self.end("leerlauf")
            elif now - self.seit >= SITZUNG_S:
                await self.end("grenze")
            elif _notaus() or not _terminal_an():
                await self.end("notaus" if _notaus() else "aus")

    def eingeben(self, data):
        os.write(self.fd, data)

    async def end(self, why):
        if self.ende.is_set():
            return
        self.ende.set()
        self.grund = why
        TERM.pop(self.id, None)
        _log_terminal(f"zu {why}", len(TERM))
        _live_text("Terminal zu")
        with contextlib.suppress(Exception):
            await self.ws.send_text(json.dumps({"typ": "zu", "grund": why}))
        with contextlib.suppress(Exception):
            await self.ws.close(1000)
        await asyncio.to_thread(self._schluss)

    def _schluss(self):
        """The program hears the terminal hang up; what stays after 5 s is stopped (the unit ends with its terminal)."""
        if self.proc is not None and self.proc.poll() is None:
            with contextlib.suppress(OSError):
                self.proc.send_signal(1)
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(OSError):
                    self.proc.kill()
                with contextlib.suppress(Exception):
                    self.proc.wait(5)
        if self.fd >= 0:
            with contextlib.suppress(OSError):
                os.close(self.fd)
            self.fd = -1



def _live_text(text):
    with contextlib.suppress(Exception):
        import live
        live.mark("entwickeln", text)


def terminal_zahlen():
    """Numbers only (Live, the page): open terminals, sessions today, refused today."""
    heute = time.strftime("%Y-%m-%d")
    if TERM_STATS["heute"] != heute:
        TERM_STATS.update(heute=heute, sitzungen=0, abgewiesen=0)
    return {"offen": len(TERM), "max": TERM_MAX, "sitzungen": TERM_STATS["sitzungen"], "abgewiesen": TERM_STATS["abgewiesen"]}


def terminal_ende(login, why):
    """Every terminal of this login (None: every one) ends; also from a thread (logging out runs in one)."""
    for s in list(TERM.values()):
        if login is None or hmac.compare_digest(s.login, login):
            with contextlib.suppress(Exception):
                asyncio.run_coroutine_threadsafe(s.end(why), s.loop)


async def notaus_close():
    """The Notaus: every terminal ends at once, no ticket stays."""
    TERM_TICKETS.clear()
    n = len(TERM)
    for s in list(TERM.values()):
        await s.end("notaus")
    if n:
        _log_terminal("notaus", n)


def _terminal_pruefen(request):
    """Switch on, an admin in the browser with a second sign-in step, no Notaus, room for one more."""
    import fernzugang
    import mfa
    if not _an() or not _terminal_an():
        _log_terminal("abgelehnt aus", 0)
        raise HTTPException(409, "Terminal im Browser ist aus (Funktionen → Entwickeln auf dem Pi → Terminal im Browser)")
    if not fernzugang.is_admin_browser(request):
        _log_terminal("abgelehnt browser", 0)
        raise HTTPException(403, "only an admin in the browser")
    prof = core.acting_profile(request)
    if not mfa.enabled(prof["id"] if prof else mfa.ADMIN):
        _log_terminal("abgelehnt zweiter_schritt", 0)
        raise HTTPException(403, "Terminal nur mit zweitem Anmeldeschritt (Ich → Sicherheit).")
    if notaus.refuse("aussen"):
        _log_terminal("abgelehnt notaus", 0)
        raise HTTPException(503, "Notaus: Terminal gesperrt")
    if len(TERM) >= TERM_MAX:
        _log_terminal("abgelehnt voll", len(TERM))
        raise HTTPException(429, "Es ist schon ein Terminal offen: erst dort „Sitzung beenden“.")


@router.post("/api/admin/entwickeln/terminal", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_terminal(request: Request):
    """„Terminal öffnen“: a fresh code every time, then a ticket that opens the WebSocket once within TICKET_S."""
    guard.limit(request, "entwickeln_terminal", None, True)
    body = await core.json_body(request, MAX_BODY_TERM, lenient=True)
    _terminal_pruefen(request)
    import fernzugang
    cols, rows = _size(body.get("cols"), body.get("rows"))
    t = secrets.token_urlsafe(32)
    now = time.time()
    for k in [k for k, v in TERM_TICKETS.items() if v["until"] < now]:
        TERM_TICKETS.pop(k, None)
    TERM_TICKETS[hashlib.sha256(t.encode()).hexdigest()] = {"login": fernzugang._login(request), "until": now + TICKET_S,
                                                            "cols": cols, "rows": rows, "who": fernzugang._who(request)}
    _log_terminal("ticket", 1)
    guard.log("entwickeln_terminal", detail="ticket")
    return {"ticket": t, "gilt_s": TICKET_S}


@router.post("/api/admin/entwickeln/terminal/beenden", dependencies=[Depends(auth)])
async def admin_terminal_beenden(request: Request):
    """„Sitzung beenden“: this login's terminal ends (ending needs no code)."""
    guard.limit(request, "entwickeln", None, True)
    await core.json_body(request, MAX_BODY, lenient=True)
    import fernzugang
    login = fernzugang._login(request)
    n = 0
    for s in list(TERM.values()):
        if hmac.compare_digest(s.login, login):
            await s.end("beendet")
            n += 1
    _log_terminal("beenden", n)
    return {"beendet": n}


async def _abweisen(ws, why, code=4403):
    TERM_STATS["abgewiesen"] = terminal_zahlen()["abgewiesen"] + 1
    _log_terminal(f"abgewiesen {why}", 0)
    with contextlib.suppress(Exception):
        await ws.close(code)


@router.websocket("/api/entwickeln/terminal")
async def terminal_ws(ws: WebSocket):
    """The browser's terminal. Its own checks, in this order: switches, Origin, admin login, Notaus, ticket, room."""
    import fernzugang
    if not _an() or not _terminal_an():
        return await _abweisen(ws, "aus", 4404)
    if not fernzugang.same_origin(ws):
        guard.log("foreign_page_refused", path="/api/entwickeln/terminal")
        return await _abweisen(ws, "fremde_seite")
    if not fernzugang.is_admin_browser(ws):
        return await _abweisen(ws, "kein_admin")
    if notaus.refuse("aussen"):
        return await _abweisen(ws, "notaus", 4503)
    raw = ws.query_params.get("t", "")
    h = hashlib.sha256(raw.encode()).hexdigest() if re.fullmatch(r"[A-Za-z0-9_\-]{30,60}", raw) else ""
    tk = TERM_TICKETS.pop(h, None) if h else None
    if not tk or tk["until"] < time.time() or not hmac.compare_digest(tk["login"], fernzugang._login(ws)):
        return await _abweisen(ws, "ticket")
    if len(TERM) >= TERM_MAX:
        return await _abweisen(ws, "voll", 4429)
    s = Terminal(tk["login"], tk["who"], tk["cols"], tk["rows"])
    s.loop = asyncio.get_running_loop()
    try:
        await asyncio.to_thread(s.starten)
    except OSError:
        return await _abweisen(ws, "start", 4502)
    await ws.accept()
    s.ws = ws
    TERM[s.id] = s
    terminal_zahlen()
    TERM_STATS["sitzungen"] += 1
    _log_terminal(f"auf {s.who}", len(TERM))
    _live_text("Terminal offen")
    q = asyncio.Queue(32)
    threading.Thread(target=s.lesen, args=(q,), name="entwickeln-terminal", daemon=True).start()
    aufgaben = [asyncio.create_task(s.zum_fenster(q)), asyncio.create_task(s.wache())]
    with contextlib.suppress(Exception):
        await ws.send_text(json.dumps({"typ": "stand", "stand": "offen", "id": s.id, "leerlauf": LEERLAUF_S // 60}))
    try:
        while not s.ende.is_set():
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            data, text = msg.get("bytes"), msg.get("text")
            if len(data or b"") > MAX_MSG or len(text or "") > MAX_MSG:
                await s.end("zu_gross")
                break
            if _notaus() or not _terminal_an():
                await s.end("notaus" if _notaus() else "aus")
                break
            s.zuletzt = time.time()
            if data:
                await asyncio.to_thread(s.eingeben, data)
            elif text:
                try:
                    m = json.loads(text)
                except ValueError:
                    continue
                if isinstance(m, dict) and m.get("typ") == "groesse":
                    c, r = _size(m.get("cols"), m.get("rows"))
                    if s.fd >= 0:
                        await asyncio.to_thread(_winsize, s.fd, c, r)
                elif isinstance(m, dict) and m.get("typ") == "ende":
                    s.grund = "beendet"
                    break
    except WebSocketDisconnect:
        pass
    except (RuntimeError, OSError):
        pass
    finally:
        await s.end(s.grund or "fenster")
        for a in aufgaben:
            a.cancel()


# ---------------------------------------------------------------- package 3b: the Code-Aufträge on the page
AUFTRAG_WARTEN_S = 90    # „Lokal einspielen“ of an order: how long the panel waits for root to move lokal forward


@router.get("/api/admin/entwickeln/auftraege", dependencies=[Depends(auth)])
async def admin_auftraege(request: Request):
    """The last Code-Aufträge for the page: goal, state, numbers and the change as text (the page shows it as text)."""
    guard.limit(request, "entwickeln", None, True)
    import codeauftrag
    if not codeauftrag.an():
        return {"an": False, "auftraege": []}
    liste = await asyncio.to_thread(codeauftrag.auftraege)
    return {"an": True, "auftraege": [{k: v for k, v in x.items() if k != "von"} for x in liste]}


async def _auftrag_wunsch(request, aktion):
    """The order of the body, still there and ready; then the wish and root's oneshot."""
    import codeauftrag
    guard.limit(request, "entwickeln_auftrag", None, True)
    body = await core.json_body(request, MAX_BODY_GH, lenient=True)
    if not codeauftrag.an():
        print(f"entwickeln: auftrag {aktion} abgelehnt aus", flush=True)
        raise HTTPException(409, entwickeln.AUFTRAG_GRUENDE["aus"][0])
    aid = str(body.get("id") or "")
    x = next((y for y in await asyncio.to_thread(codeauftrag.auftraege) if y["id"] == aid), None)
    if x is None or x["zustand"] != "fertig":
        print(f"entwickeln: auftrag {aktion} abgelehnt weg", flush=True)
        raise HTTPException(409, entwickeln.AUFTRAG_GRUENDE["weg"][0])
    codeauftrag._wunsch({"aktion": aktion, "id": aid})
    if not await asyncio.to_thread(codeauftrag._starten):
        print(f"entwickeln: auftrag {aktion} abgelehnt start", flush=True)
        raise HTTPException(500, "Code-Auftrag konnte nicht starten (sudo ./install.sh --entwickeln einmal neu)")
    print(f"entwickeln: auftrag {aktion} gestartet", flush=True)
    guard.log("entwickeln_auftrag", detail=aktion)
    return aid


@router.post("/api/admin/entwickeln/auftrag/lokal", dependencies=[Depends(auth), Depends(admin_code_fresh)])
async def admin_auftrag_lokal(request: Request):
    """„Lokal einspielen“ of an order: root moves lokal forward onto the order's branch (only forward), then the
    same install as „Lokal einspielen“ (checked, quick-tested, like an update)."""
    import codeauftrag
    t0 = int(time.time())
    aid = await _auftrag_wunsch(request, "lokal")
    ende = time.time() + AUFTRAG_WARTEN_S
    while time.time() < ende:
        await asyncio.sleep(1)
        x = next((y for y in await asyncio.to_thread(codeauftrag.auftraege) if y["id"] == aid), None)
        if x and x["zustand"] == "lokal":
            return await _wunsch(request, "einspielen")
        if x and x.get("grund") and x["t"] >= t0:     # root's answer to this wish, not a reason of an earlier try
            print(f"entwickeln: auftrag lokal abgelehnt {x['grund']}", flush=True)
            raise HTTPException(409, entwickeln.AUFTRAG_GRUENDE[x["grund"]][0])
    print("entwickeln: auftrag lokal abgelehnt zeit", flush=True)
    raise HTTPException(504, "Root hat lokal nicht rechtzeitig weitergesetzt (sudo speech-spark logs entwickeln).")


@router.post("/api/admin/entwickeln/auftrag/verwerfen", dependencies=[Depends(auth), Depends(admin_code)])
async def admin_auftrag_verwerfen(request: Request):
    """„Verwerfen“ of an order: root deletes its branch in spark-dev's clone; nothing was installed."""
    await _auftrag_wunsch(request, "weg")
    return {"gestartet": True}
