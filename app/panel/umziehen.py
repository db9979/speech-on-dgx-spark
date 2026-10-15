"""Umziehen (plan Raspberry-Pi split, B6c): the panel moves to another computer, or comes back, in one go.

The computer that gives the panel (`sudo speech-spark umziehen --code`) makes a move backup (backup.create with a
random password, so the vault key travels sealed) and hands it, with the panel's https certificate and key (the apps
pinned them), to teilen.py, which sends it inside the pairing (TLS 1.3, signed with the code's key). The computer
that takes it (`sudo speech-spark umziehen --von <host>`, or the pairing of `install.sh --mode panel`) restores it
here with the checks of the settings page (system._check_config) and the move password, and counts the profiles.
Only when that worked does the giving computer switch its role; nothing is deleted on either side.

Both run as the panel's service user; root only pipes bytes through its own temporary folder (never a path of the
service user), so stdin and stdout carry everything:

    python3 umziehen.py packen       stdin: the password line;  stdout: header line (JSON: cert, key), then the backup
    python3 umziehen.py auspacken    stdin: header line (JSON: passwort, cert, key), then the backup;
                                     stdout: {"profile": n, "wiederhergestellt": [...]}

Logs ("teilen: umzug …" lines) carry counts and fixed words only.
"""
import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # common.py, also as a script
from common import STATE, TLS_DIR, read_json, write_json  # noqa: E402

MAX_HEAD = 64 * 1024
PEM_MAX = 16 * 1024
CERT, KEY = os.path.join(TLS_DIR, "cert.pem"), os.path.join(TLS_DIR, "key.pem")
HINWEIS = os.path.join(STATE, "umzug-hinweis.json")
HINWEIS_TAGE = 14


def hinweis(now=None):
    """True for HINWEIS_TAGE days after a move to this computer: Zustand → Update lists what stays to do by hand
    (port forwards, Home Assistant, speakers), each with its way in the panel."""
    now = time.time() if now is None else now
    seit = (read_json(HINWEIS, {}) or {}).get("seit")
    return isinstance(seit, int) and 0 <= now - seit < HINWEIS_TAGE * 86400


def _read(path):
    try:
        with open(path) as f:
            return f.read(PEM_MAX)
    except OSError:
        return ""


def packen(stdin, stdout):
    """The move backup with the panel's certificate; returns the backup's entry."""
    import backup
    pw = stdin.readline(backup.MOVE_MAX + 2).strip()
    entry = backup.create(why="move", password=pw)
    head = {"cert": _read(CERT), "key": _read(KEY)}
    stdout.write(json.dumps(head, separators=(",", ":")).encode() + b"\n")
    try:
        with open(backup.path_of(entry["name"]), "rb") as f:
            shutil.copyfileobj(f, stdout, 1024 * 1024)
        stdout.flush()
    finally:
        backup.remove(entry["name"])     # sealed with a password nobody keeps: of no use in the list
    print(f"teilen: umzug gepackt {int(entry.get('size') or 0)}", file=sys.stderr, flush=True)
    return entry


def _pem_ok(text, kind):
    return isinstance(text, str) and len(text) <= PEM_MAX and f"-----BEGIN {kind}" in text and "-----END" in text


def _cert_setzen(cert, key):
    """The panel's https certificate of the giving computer (the apps pinned it); only a matching pair."""
    if not (_pem_ok(cert, "CERTIFICATE") and _pem_ok(key, "")):
        return False
    import ssl
    os.makedirs(TLS_DIR, mode=0o700, exist_ok=True)
    tmp = tempfile.mkdtemp(dir=TLS_DIR)
    try:
        c, k = os.path.join(tmp, "cert.pem"), os.path.join(tmp, "key.pem")
        with open(c, "w") as f:
            f.write(cert)
        with open(os.open(k, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
            f.write(key)
        try:
            ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(c, k)
        except (ssl.SSLError, OSError):
            return False
        os.replace(k, KEY)
        os.replace(c, CERT)
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def auspacken(stdin, stdout):
    """Restores the move backup from stdin; raises ValueError when it does not fit (nothing changed then)."""
    import backup
    import profiles
    import system
    try:
        head = json.loads(stdin.readline(MAX_HEAD) or b"null")
    except ValueError:
        head = None
    if not isinstance(head, dict) or not isinstance(head.get("passwort"), str):
        raise ValueError("kopf")
    with tempfile.TemporaryFile() as tmp:
        shutil.copyfileobj(stdin, tmp, 1024 * 1024)
        if tmp.tell() > backup.MAX_UPLOAD:
            raise ValueError("gross")
        tmp.seek(0)
        done = backup.restore(tmp, system._check_config, head["passwort"])
    cert = _cert_setzen(head.get("cert"), head.get("key"))
    write_json(HINWEIS, {"seit": int(time.time())})      # Zustand → Update: what stays to do by hand
    n = len(profiles.user_ids())
    out = {"profile": n, "wiederhergestellt": list(done), "zertifikat": cert}
    stdout.write(json.dumps(out).encode() + b"\n")
    stdout.flush()
    print(f"teilen: umzug eingespielt {n}", file=sys.stderr, flush=True)
    return out


def main(argv):
    cmd = argv[0] if argv else ""
    try:
        if cmd == "packen":
            packen(sys.stdin, sys.stdout.buffer)
        elif cmd == "auspacken":
            auspacken(sys.stdin.buffer, sys.stdout.buffer)
        else:
            print("teilen: umzug befehl unbekannt (umziehen.py packen|auspacken)", file=sys.stderr)
            return 2
    except (ValueError, OSError, EOFError) as e:
        # where it stopped, never the message; a check turned into ValueError (system._check_config) also names the
        # check that said no
        from common import fehler_stelle
        print(f"teilen: umzug abgelehnt | {fehler_stelle(e)}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
