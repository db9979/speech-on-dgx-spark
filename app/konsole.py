"""Spark-Konsole (plan spark-entkoppeln E4, Dominik 2026-11-14 „Beides“: the panel's code in a console mode with the
slim look of the pictures 4-7-b): the model computer's own web page, so a Spark without a Pi (or beside it) can be
looked after in a browser. The same panel process (panel/panel.py) started with SPEECH_SPARK_KONSOLE=1 serves only
https on konsole.port, only to the home networks of konsole.netze (and this machine), only the paths in WEGE, and
konsole.html instead of the assistant. Login, second step, codes, rate limits and the change log are the panel's own.

Off by default (konsole.an). On only by root: `sudo speech-spark konsole an <netz> [netz …]` (writes the config,
makes the certificate, enables the unit, builds the door's firewall anew), `… aus` the other way. No assistant, no
profiles, no tools: the console only shows and changes what the Spark itself runs.
"""
import ipaddress
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mandanten  # noqa: E402
from common import CONFIG_PATH, STATE, load_config, write_json  # noqa: E402
from mandanten import Fehler, netz_pruefen  # noqa: E402

ENV = "SPEECH_SPARK_KONSOLE"
UNIT = "speech-spark-konsole"
PORT = 31010
MAX_NETZE = 8
EIGENE = "/api/konsole"   # paths only the console has; the panel answers them with 404 before any login
# the only paths the console answers (prefixes); everything else is 404 before any route reads the request
WEGE = ("/static/", "/favicon.ico", "/api/login", "/api/logout", "/api/whoami", "/api/status", "/api/logs/",
        "/api/update", "/api/admin/spark-clients", "/api/admin/modelle", EIGENE)
SEITE = "/"
# "Assistent koppeln" (E4b): the console starts this fixed root unit (sudoers: exactly this command), which runs
# `speech-spark teilen code --konsole`; teilen.py writes the code into KOPPEL_CODE while it is valid, then the outcome
KOPPEL_CODE = os.path.join(STATE, "koppelcode.json")
KOPPEL_UNIT = "speech-spark-koppelcode"
KOPPEL_ENDE = ("gekoppelt", "abgelaufen", "abgelehnt", "fehler")
KOPPEL_ZEIGEN = 3600   # how long the outcome stays on the page
CODE_RE = re.compile(r"[A-Z2-9]{3}-[A-Z2-9]{3}")
FINGER_RE = re.compile(r"[0-9A-F]{2}(?::[0-9A-F]{2}){31}")


def aktiv():
    """True in the process that runs as the console."""
    return os.environ.get(ENV) == "1"


def teil(cfg=None):
    cfg = load_config() if cfg is None else cfg
    k = cfg.get("konsole") if isinstance(cfg.get("konsole"), dict) else {}
    return k


def an(cfg=None):
    return teil(cfg).get("an") is True


def port(cfg=None):
    p = teil(cfg).get("port", PORT)
    return p if isinstance(p, int) and not isinstance(p, bool) and 1024 < p <= 31099 else PORT


def netze(cfg=None):
    """The checked home networks the console answers to; [] while it is off."""
    if not an(cfg):
        return []
    out = []
    for n in (teil(cfg).get("netze") or [])[:MAX_NETZE]:
        try:
            out.append(ipaddress.ip_network(netz_pruefen(n)))
        except Fehler:
            continue
    return out


def erlaubt(host, cfg=None):
    """True for this machine and, while the console is on, for an address of konsole.netze."""
    return mandanten.adresse_in(host, netze(cfg))


def weg_ok(path):
    return path == SEITE or any(path == w or path.startswith(w.rstrip("/") + "/") or path == w.rstrip("/")
                                for w in WEGE)


def nur_konsole(path):
    return path == EIGENE or path.startswith(EIGENE + "/")


def schalten(ein, netze_neu, wer="root"):
    """konsole.an and konsole.netze into this computer's config (root's CLI; the unit and the firewall follow there)."""
    if not isinstance(ein, bool) or not isinstance(netze_neu, list) or len(netze_neu) > MAX_NETZE:
        raise Fehler("wert")
    liste = sorted({netz_pruefen(n) for n in netze_neu})
    if ein and not liste:
        raise Fehler("netz")
    with open(CONFIG_PATH) as f:
        raw = json.load(f)
    raw["konsole"] = dict(raw.get("konsole") if isinstance(raw.get("konsole"), dict) else {}, an=ein, netze=liste,
                          port=port(raw))
    write_json(CONFIG_PATH, raw, indent=2)
    print(f"konsole: {wer} {'an' if ein else 'aus'} netze {len(liste)}", flush=True)
    return {"an": ein, "netze": liste, "port": port(raw)}


def koppeln_stand(now=None, pfad=None):
    """What the console shows under "Assistent koppeln": {code, bis, fingerabdruck} while a code lives, else
    {stand} for an hour after the end, else {}. Only checked shapes leave this function."""
    now = time.time() if now is None else now
    try:
        with open(pfad or KOPPEL_CODE) as f:
            d = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(d, dict):
        return {}
    bis, t = d.get("bis"), d.get("t")
    if isinstance(bis, int) and now < bis and CODE_RE.fullmatch(str(d.get("code") or "")):
        f = str(d.get("fingerabdruck") or "")
        return {"code": d["code"], "bis": bis, "rest": int(bis - now), "fingerabdruck": f if FINGER_RE.fullmatch(f) else ""}
    if d.get("stand") in KOPPEL_ENDE and isinstance(t, int) and 0 <= now - t < KOPPEL_ZEIGEN:
        return {"stand": d["stand"], "t": t}
    return {}


def koppeln_starten():
    """Start the root unit that shows a code (the panel's sudoers line); False when it did not start."""
    try:
        ok = subprocess.run(["sudo", "-n", "/usr/bin/systemctl", "start", "--no-block", KOPPEL_UNIT], timeout=20,
                            capture_output=True, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    print(f"konsole: koppeln {'gestartet' if ok else 'fehler'}", flush=True)
    return ok


def zustand(cfg=None):
    cfg = load_config() if cfg is None else cfg
    return {"an": an(cfg), "netze": [str(n) for n in netze(cfg)], "port": port(cfg)}


def _cli(argv):
    """speech-spark konsole status|an <netz> [netz …]|aus (root runs it as the service user)."""
    cmd = argv[0] if argv else "status"
    try:
        if cmd == "status":
            z = zustand()
            print(f"Spark-Konsole: {'an' if z['an'] else 'aus'}, Port {z['port']}, Netze {', '.join(z['netze']) or '-'}")
            return 0
        if cmd == "an":
            schalten(True, argv[1:])
            return 0
        if cmd == "aus":
            schalten(False, [])
            return 0
    except Fehler as e:
        print(f"konsole: abgelehnt {e}", flush=True)
        return 2
    print("speech-spark konsole status|an <netz> [netz …]|aus", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
