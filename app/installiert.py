"""Schwachstellen, what a computer really has installed (Dominik 2026-11-13 „1“, Paket 3): the one place that reads it,
on the panel's computer for itself and in the Wärter on the model computer (tarswart.py, command `pakete`).

- venvs: the Python packages of every environment PREFIX/venv-* (the engines' venvs on tars are not locked: what pip
  took on the day of the install is what runs). Read from the folder names NAME-VERSION.dist-info only: no file is
  opened, nothing is imported or run.
- abbilder: the Python packages inside the engines' Docker images (modelle.DOCKER). An image is only read once per
  digest (the digest pins its content): `docker run` with a fixed command, no network, read-only, no GPU, the
  result kept in STATE/installiert-abbilder.json. The read runs in the background; until it is done the image counts
  as „noch nicht gelesen“.
What leaves the computer: package names and versions in a fixed character set (NAME, VER), counts. Never a path.
"""
import glob
import json
import os
import re
import subprocess
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import PREFIX, STATE, read_json, write_json  # noqa: E402

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\-]{0,63}")
VER = re.compile(r"[0-9][0-9A-Za-z.+!\-]{0,39}")
VENV = re.compile(r"venv-([a-z0-9\-]{1,20})")
IMAGE = re.compile(r"[a-z0-9][a-z0-9._/\-]{0,99}@sha256:[0-9a-f]{64}")
MAX_VENVS = 12
MAX_PAKETE = 1500          # per venv or image
ABBILD_FILE = os.path.join(STATE, "installiert-abbilder.json")
ABBILD_TIMEOUT = 120
# printed inside the image: one "name==version" line per installed distribution (the image's own python, isolated)
ABBILD_CODE = ("import importlib.metadata as m\n"
               "for d in m.distributions():\n"
               "    print(str(d.metadata['Name'] or '') + '==' + str(d.version or ''))\n")
_lock = threading.Lock()
_running = set()


def norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def _sauber(pak):
    """{name: version} with only names and versions in the fixed character set, at most MAX_PAKETE."""
    out = {}
    for n, v in (pak or {}).items() if isinstance(pak, dict) else ():
        if isinstance(n, str) and isinstance(v, str) and NAME.fullmatch(n) and VER.fullmatch(v):
            out[norm(n)] = v
        if len(out) >= MAX_PAKETE:
            break
    return out


def venv_pakete(venv):
    """{name: version} of one environment, from the folder names *.dist-info in its site-packages."""
    out = {}
    for d in glob.glob(os.path.join(venv, "lib", "python3*", "site-packages", "*.dist-info")):
        base = os.path.basename(d)[:-len(".dist-info")]
        name, _, ver = base.partition("-")
        if name and ver:
            out[name] = ver
    return _sauber(out)


def venvs(prefix=PREFIX):
    """{venv name: {name: version}} of PREFIX/venv-* (the old copies venv-*.alt are left out)."""
    out = {}
    for v in sorted(glob.glob(os.path.join(prefix, "venv-*"))):
        m = VENV.fullmatch(os.path.basename(v))
        if m and os.path.isdir(v):
            out[m.group(1)] = venv_pakete(v)
        if len(out) >= MAX_VENVS:
            break
    return out


def _abbild_lesen(image, run=subprocess.run):
    """The packages inside one image: its own python, isolated, no network, read-only, removed after."""
    r = run(["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
             "--security-opt", "no-new-privileges", "--entrypoint", "python3", image, "-I", "-c", ABBILD_CODE],
            capture_output=True, text=True, timeout=ABBILD_TIMEOUT)
    if r.returncode != 0:
        return None
    out = {}
    for line in r.stdout.splitlines()[:MAX_PAKETE * 2]:
        n, _, v = line.strip().partition("==")
        out[n] = v
    return _sauber(out)


def _abbild_bg(image, run):
    try:
        pak = _abbild_lesen(image, run)
    except (OSError, subprocess.SubprocessError):
        pak = None
    with _lock:
        _running.discard(image)
        d = read_json(ABBILD_FILE, {})
        d = d if isinstance(d, dict) else {}
        d[image] = pak if pak is not None else {"_fehler": "1"}
        write_json(ABBILD_FILE, {k: v for k, v in d.items() if IMAGE.fullmatch(k)}, mode=0o600)
        print(f"waerter: abbild gelesen {'ok' if pak is not None else 'fehler'} {len(pak or {})}", flush=True)


def abbilder(images, run=subprocess.run, start=True):
    """{image name: {name: version} | None}: read images from the store; one not read yet is read in the background
    (start) and counts as None until then. images are the digest-pinned names of modelle.DOCKER."""
    d = read_json(ABBILD_FILE, {})
    d = d if isinstance(d, dict) else {}
    out = {}
    for image in images:
        if not isinstance(image, str) or not IMAGE.fullmatch(image):
            continue
        name = image.split("@")[0]
        pak = d.get(image)
        if isinstance(pak, dict) and "_fehler" not in pak:
            out[name] = _sauber(pak)
            continue
        out[name] = None
        if start and pak is None:
            with _lock:
                if image in _running:
                    continue
                _running.add(image)
            threading.Thread(target=_abbild_bg, args=(image, run), daemon=True).start()
    return out


def lesen(images=(), prefix=PREFIX, run=subprocess.run, start=True):
    """What this computer has installed: {"venvs": {...}, "abbilder": {...}} (names and versions only)."""
    return {"venvs": venvs(prefix), "abbilder": abbilder(images, run, start)}


def fremd(r):
    """The model computer's answer, checked again here: the same shape, the same character set, or None."""
    if not isinstance(r, dict) or not isinstance(r.get("venvs"), dict):
        return None
    out = {"venvs": {}, "abbilder": {}}
    for k, v in list(r["venvs"].items())[:MAX_VENVS]:
        if isinstance(k, str) and re.fullmatch(r"[a-z0-9\-]{1,20}", k):
            out["venvs"][k] = _sauber(v)
    ab = r.get("abbilder") if isinstance(r.get("abbilder"), dict) else {}
    for k, v in list(ab.items())[:MAX_VENVS]:
        if isinstance(k, str) and re.fullmatch(r"[a-z0-9][a-z0-9._/\-]{0,99}", k):
            out["abbilder"][k] = _sauber(v) if isinstance(v, dict) else None
    return out


if __name__ == "__main__":
    print(json.dumps({k: len(v) for k, v in venvs().items()}))
