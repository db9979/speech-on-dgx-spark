"""Konsole des IT-Krisenspiels (plan krisenspiel/plan.md, Paket 2, Dominik 2026-10-22 „1a 2b 3a“, „Befehle erweitern,
damit wir auch cmd in der Linux-Welt erlernen“, „-h als Hilfe“, „durchsimuliert“): a simulated terminal under the
chronicle. Nothing a player types is ever run: there is no shell, no process, no network and no file access. The
panel cuts each line by fixed rules (at most MAX_ZEILE characters from OK_CHARS, never ${ or $(, quotes by shlex, pipes
only into PIPES, one > or >> at the end) and looks it up:
- the commands of the scenario and the general ones (krisenspiel_konsole.json) turn a line into a move of the game
  (the same move as its button, same fixed effects), into a wrong move with its own effects (falsch: the wrong VM,
  the own admin account) or into fixed output read from the game's state (ausgabe, lines with conditions);
- the Linux commands (krisenlinux.LINUX, about 150) are simulated on the machines of the scenario: a file system per
  machine, users, mounts, firewall rules, services; sudo where Linux needs root; stopping a service of a system of
  the game, kill or reboot come back as a move with fixed effects (wirkung);
- the console's own commands, the Windows ones and the game's ones (BEFEHLE) answer from the simulated world;
- every command answers -h, --help and /? with its help (man too), a typo gets „Meintest du …?“, anything else is
  "command not found". The language model never writes console output and never decides an effect.
Reading costs game time: every reading command adds a minute that the next move takes along; LESEN_MAX minutes of
reading are a move of their own („Analyse an der Konsole“), so time and events go on. Every game starts on jump01,
the admin's Linux jump host.

run() is pure: it gets the state and the moves offered and returns the output and what the caller (krisenspiel.py)
has to do, so it can be tested without the panel."""
import difflib
import json
import os
import re
import shlex

import krisenlinux

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "krisenspiel_konsole.json")
MAX_ZEILE = 200          # characters of a typed line
PUFFER = 300             # console lines kept in a game
VERLAUF = 50             # typed lines kept for ↑/↓
LESEN_MAX = 10           # minutes of reading that become a move of their own
AUSGABE_MAX = 60         # lines of output of one command
OK_CHARS = re.compile(r"^[A-Za-z0-9 _.:/=,@*'\"|\\+~?>$^()\[\]{}-]*$")
NIE = ("${", "$(")       # never, even inside quotes
PIPES = ("grep", "egrep", "fgrep", "head", "tail", "wc", "sort", "uniq", "cut", "awk", "sed", "tr", "tac", "nl",
         "column", "cat", "less", "more", "tee", "sudo")
HFLAG = {"df", "du", "free", "ls", "sort", "shutdown"}   # there -h is an option, not the help
OS_NAMES = {"win": "Windows Server 2022", "linux": "Debian 12", "net": "network OS", "san": "storage OS",
            "ups": "UPS firmware", "gen": "genset controller", "pbx": "PBX"}
WIN = ("win",)
UNIX = krisenlinux.U
# the console's own, the Windows and the game's commands: name -> (where or None everywhere, kind, help de, help en,
# usage). kind: "frei" costs nothing, "lesen" costs a minute, "spiel" only does something through the scenario's lines.
# The Linux commands are krisenlinux.LINUX; no name is in both (check_data).
BEFEHLE = {
    "help": (None, "frei", "Die Befehle in Gruppen", "The commands in groups", "help [gruppe|befehl]"),
    "man": (None, "frei", "Hilfe zu einem Befehl", "Help on a command", "man <befehl>"),
    "clear": (None, "frei", "Konsole leeren", "Clear the console", "clear"),
    "history": (None, "frei", "Die letzten Eingaben", "The last inputs", "history"),
    "hosts": (None, "frei", "Die Rechner dieses Szenarios", "The machines of this scenario", "hosts"),
    "ssh": (None, "frei", "Auf einen anderen Rechner wechseln", "Switch to another machine", "ssh <rechner>"),
    "exit": (None, "frei", "Zurück zu jump01", "Back to jump01", "exit"),
    "team": (None, "frei", "Die Kollegen, ihre Fächer, Müdigkeit und Aufgaben", "The colleagues, their subjects, tiredness and tasks", "team"),
    "assign": (None, "frei", "Eine Aufgabe an einen Kollegen geben (ohne Angabe: was geht)", "Hand a task to a colleague (without: what can be handed over)", "assign <kollege> <aufgabe>"),
    "dir": (WIN, "frei", "Dateien auflisten", "List files", "dir [pfad]"),
    "type": (WIN, "lesen", "Datei zeigen", "Show a file", "type <datei>"),
    "tracert": (WIN, "lesen", "Weg zu einem Rechner", "Route to a machine", "tracert <rechner|ip>"),
    "ipconfig": (WIN, "lesen", "Adressen", "Addresses", "ipconfig"),
    "get-service": (WIN, "lesen", "Dienste", "Services", "Get-Service"),
    "get-winevent": (WIN, "spiel", "Ereignisprotokoll lesen", "Read the event log", "Get-WinEvent -LogName <name>"),
    "stop-service": (WIN, "spiel", "Dienst anhalten", "Stop a service", "Stop-Service <dienst>"),
    "disable-adaccount": (WIN, "spiel", "AD-Konto sperren", "Disable an AD account", "Disable-ADAccount <konto>"),
    "set-adaccountpassword": (WIN, "spiel", "Passwörter zurücksetzen", "Reset passwords", "Set-ADAccountPassword -Reset"),
    "remove-aduser": (WIN, "spiel", "AD-Konto entfernen", "Remove an AD account", "Remove-ADUser <konto>"),
    "vssadmin": (WIN, "spiel", "Schattenkopien", "Shadow copies", "vssadmin list shadows"),
    "stop-vm": (None, "spiel", "VMs anhalten", "Stop VMs", "Stop-VM <name|-Tag tag>"),
    "start-vm": (None, "spiel", "VMs starten", "Start VMs", "Start-VM *"),
    "restart-vm": (None, "spiel", "VMs neu starten", "Restart VMs", "Restart-VM *"),
    "multipath": (UNIX, "spiel", "Speicherpfade", "Storage paths", "multipath -ll"),
    "porterrshow": (UNIX, "spiel", "Fehler an FC-Ports", "Errors on FC ports", "porterrshow"),
    "controller": (UNIX, "spiel", "Storage-Controller", "Storage controllers", "controller show | controller failover"),
    "firmware": (UNIX, "spiel", "Firmware einspielen", "Install firmware", "firmware install"),
    "disk": (UNIX, "spiel", "Platten tauschen", "Replace disks", "disk replace"),
    "sfp": (UNIX, "spiel", "SFP tauschen", "Replace an SFP", "sfp replace <port>"),
    "sqlcmd": (WIN, "spiel", "SQL-Befehl", "SQL command", "sqlcmd -Q \"DBCC CHECKDB\""),
    "a2ensite": (UNIX, "spiel", "Webseite einschalten", "Enable a site", "a2ensite <seite>"),
    "upsc": (None, "spiel", "USV-Werte", "UPS values", "upsc usv01"),
    "ipmitool": (UNIX, "spiel", "Sensoren", "Sensors", "ipmitool sensor"),
    "genset": (UNIX, "spiel", "Notstrom", "Generator", "genset start"),
    "callforward": (UNIX, "spiel", "Rufumleitung", "Call forwarding", "callforward on"),
    "power-on": (None, "spiel", "Strom einschalten", "Power on", "power-on sequence | power-on all"),
    "show": (UNIX, "spiel", "Router-Zustand", "Router state", "show bgp"),
    "network": (UNIX, "spiel", "Präfix ankündigen", "Announce a prefix", "network <präfix>"),
    "whois": (None, "spiel", "Netz-Besitzer", "Network owner", "whois <AS>"),
    "lg": (None, "spiel", "Looking Glass", "Looking glass", "lg <präfix>"),
    "roa": (None, "spiel", "RPKI-ROA", "RPKI ROA", "roa add <präfix>"),
    "crtsh": (None, "spiel", "Certificate-Transparency-Logs", "Certificate transparency logs", "crtsh <domain>"),
    "revoke": (None, "spiel", "Zertifikat widerrufen", "Revoke a certificate", "revoke cert"),
    "restic": (UNIX, "spiel", "Backup prüfen", "Check a backup", "restic check"),
    "restore": (None, "spiel", "Wiederherstellen", "Restore", "restore backup|shadow|exchange|db"),
    "apply": (UNIX, "spiel", "Patch oder Workaround", "Patch or workaround", "apply patch|workaround"),
    "reimage": (None, "spiel", "Gerät neu aufsetzen", "Set a device up again", "reimage <rechner>"),
    "shutdown": (None, "spiel", "Herunterfahren", "Shut down", "shutdown -h now"),
    "repair": (None, "spiel", "Reparatur beauftragen", "Order a repair", "repair <teil>"),
    "call": (None, "spiel", "Jemanden anrufen", "Call someone", "call <wer>"),
    "mail": (None, "spiel", "Jemandem schreiben", "Write to someone", "mail <wer>"),
    "announce": (None, "spiel", "Etwas ankündigen", "Announce something", "announce <was>"),
    "order": (None, "spiel", "Etwas bestellen", "Order something", "order <was>"),
    "meeting": (None, "spiel", "Lagebesprechung", "Status meeting", "meeting"),
    "wait": (None, "spiel", "Abwarten", "Wait", "wait"),
    "sleep": (UNIX, "spiel", "Abwarten", "Wait", "sleep 300"),
    # Paket 4: the commands of the new scenarios
    "geoblock": (None, "spiel", "Länder an der Firewall sperren", "Block countries at the firewall", "geoblock <land>"),
    "scale": (None, "spiel", "Server hochskalieren", "Scale servers up", "scale web <anzahl>"),
    "pay": (None, "spiel", "Eine Forderung bezahlen", "Pay a demand", "pay <wer>"),
    "aws": (None, "spiel", "Cloud-Konsole des Anbieters", "The provider's cloud console", "aws status|support|failover|restore|ls|private <bucket>"),
    "dns": (None, "spiel", "DNS-Einträge umstellen", "Change DNS records", "dns switch | dns region"),
    "risk": (None, "spiel", "Risiko für Betroffene bewerten", "Assess the risk for the people affected", "risk"),
    "image": (None, "spiel", "Beweis-Image eines Geräts ziehen", "Take a forensic image of a device", "image <rechner>"),
    "blocklist": (None, "spiel", "Domains an Firewall, DNS und Mailfilter sperren", "Block domains at firewall, DNS and mail filter", "blocklist add <domain>"),
    "get-aduser": (WIN, "spiel", "AD-Konten zeigen", "Show AD accounts", "Get-ADUser -Filter *"),
    "get-inboxrule": (WIN, "spiel", "Regeln eines Postfachs", "Rules of a mailbox", "Get-InboxRule -Mailbox <name>"),
    "crontab": (UNIX, "spiel", "Geplante Aufgaben", "Scheduled tasks", "crontab -l | crontab -r"),
    "apt": (UNIX, "spiel", "Pakete verwalten", "Manage packages", "apt remove <paket>"),
    "mysql": (UNIX, "spiel", "Datenbank-Befehl", "Database command", "mysql -e \"STOP REPLICA\""),
    "mysqlbinlog": (UNIX, "spiel", "Transaktionslogs nachspielen", "Replay transaction logs", "mysqlbinlog --stop-datetime=<zeit>"),
}
# the extra groups of „help“ besides krisenlinux.GRUPPEN
EIGENE = {"konsole": ("Konsole", "Console"), "windows": ("Windows", "Windows"), "spiel": ("Im Spiel", "In the game")}
STATUS_DIENST = {"Online": "Running", "Degraded": "Running (degraded)", "Critical": "Stopped", "Offline": "Stopped",
                 "Isolated": "Running (isolated)"}


def _load():
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


_DATA = _load()


def check_data(szenarien, actions, d=None):
    """The console data against the scenarios: commands known, hosts and assets exist, every move reachable by typing
    (so a game in the mode „nur Konsole“ can be won). szenarien: id -> scenario, actions: the general actions."""
    d = _DATA if d is None else d
    bad = [f"befehl twice: {n}" for n in sorted(set(BEFEHLE) & set(krisenlinux.LINUX))]
    general = {a["id"] for a in actions}

    def entry(e, where, ids, hosts):
        if e.get("befehl") not in BEFEHLE and e.get("befehl") not in krisenlinux.LINUX:
            bad.append(f"{where}: befehl {e.get('befehl')}")
        if set(e) - {"befehl", "args", "host", "zug", "ausgabe", "falsch"}:
            bad.append(f"{where}: keys")
        if e.get("host") and e["host"] not in hosts:
            bad.append(f"{where}: host {e['host']}")
        z = e.get("zug")
        for a in ([z] if isinstance(z, str) else z or []):
            if a not in ids:
                bad.append(f"{where}: zug {a}")
        if not (z or "ausgabe" in e or e.get("falsch")):
            bad.append(f"{where}: does nothing")
        if e.get("falsch") and not isinstance(e["falsch"].get("text"), list):
            bad.append(f"{where}: falsch text")
        if any(a != a.lower() or not a for a in e.get("args", [])):
            bad.append(f"{where}: args lower case")
        return [z] if isinstance(z, str) else z or []

    typed = set()
    for i, e in enumerate(d.get("allgemein", [])):
        typed |= set(entry(e, f"allgemein {i}", general, set()))
    for sid, sz in szenarien.items():
        k = d.get("szenarien", {}).get(sid)
        if not k:
            bad.append(f"{sid}: no console")
            continue
        ids = {a["id"] for a in sz["aktionen"]} | general
        assets = {a["id"] for a in sz["assets"]}
        hosts = {h["id"] for h in k["hosts"]}
        if k["hosts"][0]["id"] != "jump01" or k["hosts"][0]["os"] != "linux":
            bad.append(f"{sid}: first host is not the linux jump01")
        for h in k["hosts"]:
            if h.get("asset") and h["asset"] not in assets or h.get("os") not in OS_NAMES:
                bad.append(f"{sid}: host {h['id']}")
        for f in k.get("dateien", []):
            if f["host"] not in hosts:
                bad.append(f"{sid}: datei {f['pfad']}")
        mine = set(typed)
        for i, e in enumerate(k.get("befehle", [])):
            mine |= set(entry(e, f"{sid} {i}", ids, hosts))
        missing = ids - mine
        if missing:
            bad.append(f"{sid}: not typeable {sorted(missing)}")
    return bad


def world(sid):
    return _DATA["szenarien"][sid]


def first_host(sid):
    return world(sid)["hosts"][0]["id"]


def fresh(sid):
    return {"host": first_host(sid), "zeilen": [], "verlauf": [], "min": 0}


def hilfe_daten(sid):
    """For the page: command names (Tab) and the machines."""
    return {"befehle": sorted(set(BEFEHLE) | set(krisenlinux.LINUX)), "hosts": [h["id"] for h in world(sid)["hosts"]]}


def ctx(st, holds, lang="de", names=None):
    """The simulation's view of the machine the console is on (krisenlinux.Ctx)."""
    sid = st["szenario"]
    k = st.setdefault("konsole", fresh(sid))
    return krisenlinux.Ctx(st, _host(sid, k["host"]), world(sid), holds, lang == "en", lambda x: _status(st, x),
                           lambda a: (names or {}).get(a, a), world(sid)["hosts"])


def tab_daten(st, holds, lang="de"):
    """For Tab on the page: the working directory and every path of the machine (directories end in /); Windows
    machines have none."""
    c = ctx(st, holds, lang)
    if not _has(c.h, UNIX):
        return {"cwd": "", "pfade": [], "editor": None}
    files, dirs = krisenlinux.tree(c)
    return {"cwd": c.cwd, "pfade": sorted([d.rstrip("/") + "/" for d in dirs if d != "/"] + list(files)),
            "editor": krisenlinux.editor_view(c)}


def _lines(lines, st, holds):
    out = []
    for x in lines:
        if isinstance(x, list):
            if holds(x[1], st):
                out.append(x[0])
        else:
            out.append(x)
    return out


def _host(sid, name):
    name = (name or "").lower()
    return next((h for h in world(sid)["hosts"] if h["id"] == name or h["ip"] == name), None)


def _status(st, h):
    return st["assets"][h["asset"]]["status"] if h and h.get("asset") else "Online"


def _has(h, where):
    return where is None or h is None or h["os"] in where


def _spec(name):
    return krisenlinux.LINUX.get(name) or BEFEHLE.get(name)


def _files(sid, host):
    return [f for f in world(sid).get("dateien", []) if f["host"] == host]


def _file(sid, host, name):
    name = name.replace("\\", "/").lower()
    for f in _files(sid, host):
        p = f["pfad"].lower()
        if p == name or p.endswith("/" + name.lstrip("./")):
            return f
    return None


def _cut(z, ch):
    """z split at every ch outside quotes (shlex rules: '…', "…", a backslash outside quotes)."""
    out, cur, q, i = [], [], "", 0
    while i < len(z):
        x = z[i]
        if q:
            if x == q:
                q = ""
            cur.append(x)
        elif x == "\\" and i + 1 < len(z):
            cur += [x, z[i + 1]]
            i += 1
        elif x in "'\"":
            q = x
            cur.append(x)
        elif x == ch:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(x)
        i += 1
    out.append("".join(cur))
    return out


def parse(zeile):
    """(tokens per pipe part, redirect (path, append) or None, error): fixed rules only; the line is never handed to
    anything that runs it."""
    z = (zeile or "").strip()
    if not z:
        return [], None, ""
    if len(z) > MAX_ZEILE or not OK_CHARS.match(z) or any(x in z for x in NIE):
        return None, None, "abgelehnt"
    segs = _cut(z, "|")
    redir = None
    if any(len(_cut(s, ">")) > 1 for s in segs[:-1]):
        return None, None, "syntax"
    r = _cut(segs[-1], ">")
    if len(r) > 1:
        if len(r) > 3 or len(r) == 3 and r[1] != "":
            return None, None, "syntax"
        try:
            target = shlex.split(r[-1], posix=True)
        except ValueError:
            return None, None, "syntax"
        if len(target) != 1:
            return None, None, "syntax"
        redir = (target[0], len(r) == 3)
        segs[-1] = r[0]
    parts = []
    for seg in segs:
        try:
            tok = shlex.split(seg, posix=True)
        except ValueError:
            return None, None, "syntax"
        if not tok:
            return None, None, "syntax"
        parts.append(tok)
    for p in parts[1:]:
        name = p[0].lower()
        if name not in PIPES or name == "sudo" and (len(p) < 2 or p[1].lower() not in PIPES):
            return None, None, "pipe:" + (p[1] if name == "sudo" and len(p) > 1 else p[0])[:30]
    return parts, redir, ""


def _match(sid, name, args, host):
    """The first data line for this command: (entry, on the right host)."""
    low = " ".join(args).lower()
    cand = list(world(sid).get("befehle", [])) + list(_DATA.get("allgemein", []))
    found = None
    for e in cand:
        if e["befehl"] != name or not all(a in low for a in e.get("args", [])):
            continue
        if not e.get("host") or e["host"] == host:
            return e, True
        found = found or e
    return found, False


def _suggest(name, h):
    names = [n for n in set(BEFEHLE) | set(krisenlinux.LINUX) if _has(h, _spec(n)[0])]
    return difflib.get_close_matches(name, names, n=1, cutoff=0.75)


def run(st, zeile, offered, holds, lang="de", names=None):
    """One typed line. offered: action id -> the available() entry; names: asset id -> its name. Returns
    {"out": [(kind, text)], "art": leer|frei|lesen|zug|falsch|wirkung|unbekannt|abgelehnt|nicht, "zug": id,
     "falsch": effect, "wirkung": a move of the simulation (a stopped service, a reboot), "clear": bool}; the caller
    writes the input line, applies a move and keeps the minute."""
    sid = st["szenario"]
    k = st.setdefault("konsole", fresh(sid))
    h = _host(sid, k["host"])
    en = lang == "en"
    res = {"out": [], "art": "frei", "zug": None, "falsch": None, "wirkung": None, "clear": False, "editor": False, "an": None}
    out = res["out"]
    parts, redir, err = parse(zeile)
    if parts == [] and not err:
        res["art"] = "leer"
        return res
    if err:
        res["art"] = "abgelehnt"
        msg = {"abgelehnt": "spark: refused: only letters, digits, spaces and _ . : / = , @ * ' \" | \\ + - ~ ? > $ ^ ( ) [ ] "
                            "{ } (no ${ or $(, at most %d)" % MAX_ZEILE,
               "syntax": "syntax error: unmatched quote, empty part or > not at the end"}.get(err) or \
            f"{err[5:]}: not allowed after | (only {', '.join(PIPES)})"
        out.append(("err", msg))
        return res
    c = krisenlinux.Ctx(st, h, world(sid), holds, en, lambda x: _status(st, x), lambda a: (names or {}).get(a, a),
                        world(sid)["hosts"])
    c.offered = offered
    tok, root = parts[0], False
    if tok[0].lower() == "sudo" and _has(h, krisenlinux.LINUX["sudo"][0]):
        if len(tok) == 1 or tok[1].lower() in ("-h", "--help", "/?"):
            out += [("out", s) for s in krisenlinux.help_lines("sudo", en)]
            return res
        if tok[1].lower() in ("-i", "-s", "su", "bash", "sh"):
            out.append(("err", "sudo: a root shell is not simulated here; put sudo in front of each command"))
            return res
        tok, root = tok[1:], True
    name, args = tok[0].lower(), tok[1:]
    if name.startswith("mkfs."):
        name = "mkfs"
    spec = _spec(name)
    if not spec or not _has(h, spec[0]):
        res["art"] = "unbekannt"
        out.append(("err", f"{tok[0][:40]}: command not found"))
        sug = _suggest(name, h)
        if sug:
            out.append(("err", ("Did you mean: " if en else "Meintest du: ") + sug[0] + "?"))
        return res
    kind = spec[2] if name in krisenlinux.LINUX else spec[1]
    if args and (args[0] in ("--help", "/?") or args == ["-h"] and name not in HFLAG):
        lines = krisenlinux.help_lines(name, en, spec)
    elif name in krisenlinux.ROOT and not root:
        lines = krisenlinux.run(c, name, args, root)          # Permission denied, no move
    else:
        lines = _answer(res, st, c, name, args, kind, offered, holds, root)
    for p in parts[1:]:
        lines = krisenlinux.pipe(c, p, lines, root)
    if redir and res["art"] != "nicht":
        if not _has(h, UNIX):
            out.append(("err", "spark: > and >> only on the Linux machines (ssh jump01)"))
        else:
            e = krisenlinux.write(c, redir[0], lines, redir[1], root)
            lines = []
            if e:
                out.append(("err", "bash: " + e))
    if c.effekt and not res["zug"] and not res["falsch"]:
        res.update(art="wirkung", wirkung=c.effekt)
    # a machine switched off ends the ssh session (Dominik 2026-10-22): back on the jump host, like exit
    bye = f"Connection to {c.hid} closed by remote host."
    if (name in ("halt", "poweroff") or name == "shutdown" and not {"-r", "--reboot"} & set(args)) \
            and (bye in lines or res["art"] in ("zug", "falsch")) and k["host"] != first_host(sid):
        lines = [x for x in lines if x != bye] + [bye]
        k["host"] = first_host(sid)
    res["editor"] = c.editor
    out += [("out", s) for s in lines[:AUSGABE_MAX]]
    if len(lines) > AUSGABE_MAX:
        out.append(("err", f"... {len(lines) - AUSGABE_MAX} more lines (use | head, | tail or | grep)"))
    return res


def _read(st, c, name, args, root, res):
    if name in krisenlinux.LINUX:
        return krisenlinux.run(c, name, args, root)
    return _builtin(st, c, name, args, res)


def _answer(res, st, c, name, args, kind, offered, holds, root):
    """A line of the scenario's data first (a move, a wrong move, fixed output), else the simulation."""
    out = res["out"]
    e, here = _match(st["szenario"], name, args, c.hid)
    if e and here:
        if e.get("zug"):
            ids = [e["zug"]] if isinstance(e["zug"], str) else e["zug"]
            pick = next((a for a in ids if a in offered), None)
            if pick and offered[pick]["frei"]:
                res.update(art="zug", zug=pick)
                return _lines(e["ausgabe"], st, holds) if "ausgabe" in e else \
                    _read(st, c, name, args, root, res) if kind != "spiel" else []
            if pick:
                res["art"] = "nicht"
                out.append(("err", f"{name}: the emergency budget is not enough"))
                return []
            if kind != "spiel":
                res["art"] = kind          # a reading command whose move is done or not yet possible: just read
                return _read(st, c, name, args, root, res)
            res["art"] = "nicht"
            out.append(("err", f"{name}: nothing to do right now (already done or not possible yet)"))
            return []
        if e.get("falsch"):
            res.update(art="falsch", falsch=e["falsch"])
            return []
        res["art"] = "lesen"
        return _lines(e["ausgabe"], st, holds)
    if name == "shutdown" and _has(c.h, krisenlinux.LINUX["poweroff"][0]):   # no move of the scenario: as on Linux
        res["art"] = "frei"
        return krisenlinux.run(c, "reboot" if {"-r", "--reboot"} & set(args) else "poweroff", [], root)
    if kind == "spiel":
        res["art"] = "nicht"
        out.append(("err", f"{name}: no such object on {c.hid}"))
        return []
    res["art"] = kind
    return _read(st, c, name, args, root, res)


def _wrap(head, words, width=100):
    rows, cur = [], head
    for w in words:
        if len(cur) + len(w) + 1 > width and cur.strip():
            rows.append(cur.rstrip())
            cur = " " * 4
        cur += w + " "
    rows.append(cur.rstrip())
    return rows


def _gruppen(h):
    """group key -> (de, en, the names on this machine) for „help“."""
    g = {}
    for key, (de, en) in krisenlinux.GRUPPEN.items():
        n = sorted(x for x, s in krisenlinux.LINUX.items() if s[1] == key and _has(h, s[0]))
        if n:
            g[key] = (de, en, n)
    own = {"konsole": [x for x, s in BEFEHLE.items() if s[1] != "spiel" and s[0] is None],
           "windows": [x for x, s in BEFEHLE.items() if s[1] != "spiel" and s[0] == WIN and _has(h, s[0])],
           "spiel": [x for x, s in BEFEHLE.items() if s[1] == "spiel" and _has(h, s[0])]}
    for key, n in own.items():
        if n:
            g[key] = EIGENE[key] + (sorted(n),)
    return g


def _what(name, en):
    s = _spec(name)
    i = 3 if name in krisenlinux.LINUX else 2
    return s[i + 1] if en else s[i]


def _help(c, args):
    en = c.en
    g = _gruppen(c.h)
    if args:
        t = args[0].lower()
        key = next((k for k, v in g.items() if t in (k, v[0].lower(), v[1].lower())), None)
        if key:
            return [g[key][1 if en else 0] + ":"] + [f"  {n:<22} {_what(n, en)}" for n in g[key][2]]
        if _spec(t):
            return krisenlinux.help_lines(t, en, _spec(t))
        return [f"help: no help topics match '{args[0][:40]}'"]
    rows = ["Commands by group, none of them really runs:" if en else "Befehle nach Gruppen, nichts davon läuft wirklich:"]
    for key, (de, en_t, n) in g.items():
        rows += _wrap(f"{en_t if en else de} (help {key}): ", n)
    rows.append("<command> -h shows the help of a command, sudo <command> runs it as root" if en else
                "<befehl> -h zeigt die Hilfe eines Befehls, sudo <befehl> führt ihn als root aus")
    rows.append(("Machines: " if en else "Rechner: ") + ", ".join(x["id"] for x in c.hosts))
    return rows


def _team(st, c, name, args, res):
    """team: the colleagues (Paket 3); assign <kollege> <aufgabe>: the same as handing a move over by button."""
    ks = st.get("kollegen") or []
    gone = st["m"]["zeit_start"] - st["m"]["zeit"]
    if name == "team":
        if not ks:
            return ["team: no colleagues in this game"]
        rows = []
        for x in ks:
            job = (c.say("arbeitet: ", "working: ") + x["auftrag"]["label"][1 if c.en else 0]
                   + f" ({c.say('noch', 'left')} {max(0, x['auftrag']['fertig'] - gone)} min)") if x["auftrag"] else c.say("frei", "free")
            rows.append(f"{x['id']:<8} {', '.join(x['faecher']):<24} {c.say('müde', 'tired')} {x['muede']:>3} %   {job}")
        return rows
    offer = [a for a in c.offered.values() if a.get("fach") and a["frei"]]
    if len(args) < 2:
        return ([c.say("Aufruf: assign <kollege> <aufgabe>, zum Beispiel assign ", "Usage: assign <colleague> <task>, for example assign ")
                 + (ks[0]["id"] if ks else "sandra") + " " + (offer[0]["id"] if offer else "logs"),
                 c.say("Aufgaben, die jetzt gehen:", "Tasks that can be handed over now:")]
                + [f"  {a['id']:<16} {a['label'][1 if c.en else 0]} ({a['fach']})" for a in offer])
    who = next((x for x in ks if args[0].lower() in (x["id"], x["name"].lower())), None)
    if not who:
        res["art"] = "nicht"
        return [f"assign: {args[0][:30]}: no such colleague (team shows them)"]
    if who["auftrag"]:
        res["art"] = "nicht"
        return [f"assign: {who['id']} is busy ({max(0, who['auftrag']['fertig'] - gone)} min left)"]
    if who["muede"] >= 100:
        res["art"] = "nicht"
        return [f"assign: {who['id']} is too tired (a status meeting or food helps)"]
    a = next((x for x in offer if x["id"] == args[1].lower()), None)
    if not a:
        res["art"] = "nicht"
        return [f"assign: {args[1][:40]}: not a task to hand over right now (assign shows them)"]
    res.update(art="zug", zug=a["id"], an=who["id"])
    return []


def _builtin(st, c, name, args, res):
    """The console's own commands and the Windows ones."""
    sid = st["szenario"]
    k = st["konsole"]
    h, en = c.h, c.en
    arg = args[0] if args else ""
    if name == "help":
        return _help(c, args)
    if name == "man":
        sp = _spec(arg.lower())
        return krisenlinux.help_lines(arg.lower(), en, sp) if sp else [f"No manual entry for {arg[:40]}"]
    if name == "clear":
        res["clear"] = True
        return []
    if name == "history":
        return [f"{i + 1:>4}  {x}" for i, x in enumerate(k["verlauf"][-20:])]
    if name == "hosts":
        return [f"{x['id']:<10} {x['ip']:<15} {OS_NAMES[x['os']]:<20} {_status(st, x)}" for x in c.hosts]
    if name == "ssh":
        t = _host(sid, next((a for a in args if not a.startswith("-")), "").split("@")[-1])
        if not t:
            return [f"ssh: Could not resolve hostname {arg[:40]}: Name or service not known"]
        k["host"] = t["id"]
        note = " (out-of-band console)" if _status(st, t) in ("Offline", "Isolated") else ""
        return [f"Connected to {t['id']} ({t['ip']}), {OS_NAMES[t['os']]}{note}"]
    if name in ("team", "assign"):
        return _team(st, c, name, args, res)
    if name == "exit":
        k["host"] = first_host(sid)
        return [f"Connection to {c.hid} closed."]
    if name == "dir":
        pre = arg.replace("\\", "/").lower()
        fs = [f["pfad"] for f in _files(sid, c.hid) if f["pfad"].lower().startswith(pre) or not pre]
        return fs or ([f"File Not Found: {arg[:60]}"] if pre else ["(empty)"])
    if name == "type":
        f = _file(sid, c.hid, arg)
        return _lines(f["zeilen"], st, c.holds) if f else [f"The system cannot find the file specified: {arg[:60]}"]
    if name == "tracert":
        t = _host(sid, arg)
        if not t:
            return [f"Unable to resolve target system name {arg[:40]}."]
        last = f"  2    <1 ms  {t['id']} [{t['ip']}]" if _status(st, t) in ("Online", "Degraded", "Critical") else \
            "  2     *        Request timed out."
        return [f"Tracing route to {t['id']} [{t['ip']}]", "  1    <1 ms  gateway", last]
    if name == "ipconfig":
        return [f"IPv4 Address. . . . . . . . . . . : {h['ip']}", "Subnet Mask . . . . . . . . . . . : 255.255.255.0"]
    if name == "get-service":
        s = STATUS_DIENST[_status(st, h)]
        ds = [d for d in h.get("dienste", []) if not arg or arg.lower() == d.lower()]
        return ["Status   Name"] + [f"{s:<8} {d}" for d in ds] if ds else \
            [f"Get-Service : Cannot find any service with service name '{arg[:40]}'."]
    return []
