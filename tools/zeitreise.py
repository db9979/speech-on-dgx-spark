#!/usr/bin/env python3
"""Zeitreise: the self-tests once more with the clock moved ahead (code review 2026-11-11, Dominik „1-11“).

    python3 tools/zeitreise.py                 every test module with the clock TAGE days ahead
    python3 tools/zeitreise.py --tage 200      another distance
    python3 tools/zeitreise.py test_tipps      only these modules
    python3 tools/zeitreise.py -j 2            two modules at the same time (default JOBS)

Why: a test with a fixed moment in it turns red by itself once the real day has moved far enough, although nobody
changed the code (main red 2026-11-11: moments of 12.10. met a 30-day window of the real clock; then no update
reaches the Spark, because it installs only versions whose "Tests" run is green). The rule „Tests hängen nicht von
der Uhrzeit ab“ had no guard. This is the guard: GitHub runs it every night (.github/workflows/zeitreise.yml) and
opens the issue „Zeitreise rot“ with the names of the tests.

How: every module runs on its own under libfaketime (`faketime -f +<TAGE>d`), which moves the whole process's
clock (time, datetime). File times must move with it, else a file written just now looks months old (three tests
were red only for that): libfaketime 0.9.10 does not catch the stat64 calls of Python 3.11, so the run first
measures it (dateizeit) and, where needed, builds and loads tools/zeitreise_stat.c next to libfaketime (needs cc);
when file times still do not follow, there is no verdict (exit code 2). All this without the page tests (they need a real browser and a real
clock for its certificates; SPEECH_SPARK_NO_BROWSER). A module red there runs once more with `faketime -f +0d`:
- green at +0d: the test depends on the date. That is red here (exit code 1) and named.
- red or stuck at +0d too: libfaketime itself disturbs it (tight time limits, child programs). That is only named
  („gestört“), never red: the normal "Tests" run is the one that tells whether the test works.
Nothing here skips or changes a test of the normal run; it is one more run with another clock. Needs the program
`faketime` (apt package faketime) and a Python with the panel's packages (the venv of tools/vorpush.py, else the
one this runs with).
"""
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
TESTS = os.path.join(APP, "tests")
TAGE = 120           # days ahead: past every 30-, 60- and 90-day window, into another month, quarter and (in autumn) year
JOBS = 4
FRIST = 900          # seconds one module may take under libfaketime
VENV_PY = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "speech-spark-vorpush",
                       "venv", "bin", "python")


def module(names=()):
    """The test modules to run: every test_*.py, or only the named ones (ValueError for an unknown name)."""
    have = sorted(f[:-3] for f in os.listdir(TESTS) if f.startswith("test_") and f.endswith(".py"))
    if not names:
        return have
    bad = [n for n in names if n not in have]
    if bad:
        raise ValueError("unknown test module: " + " ".join(bad))
    return sorted(set(names))


PROBE = ("import os, tempfile, time\nfd, p = tempfile.mkstemp()\nos.close(fd)\n"
         "print(round(time.time() - os.stat(p).st_mtime))\nos.utime(p, (time.time(), time.time()))\n"
         "print(round(time.time() - os.stat(p).st_mtime))\nos.remove(p)\n")
SHIM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "zeitreise_stat.c")
_shim = {"so": None}       # the built tools/zeitreise_stat.c, when this Python needs it (dateizeit)


def _umgebung(tage):
    env = dict(os.environ, SPEECH_SPARK_NO_BROWSER="1")
    if _shim["so"]:
        env.update(LD_PRELOAD=_shim["so"], ZEITREISE_STAT=str(int(tage) * 86400))
    return env


def _folgt(py, tage):
    """True when a file written (and one touched) under the moved clock is as old as the clock says: a few seconds."""
    try:
        r = subprocess.run(["faketime", "-f", f"+{int(tage)}d", py, "-c", PROBE], env=_umgebung(tage),
                           capture_output=True, timeout=60)
        return r.returncode == 0 and all(abs(int(z)) < 60 for z in r.stdout.split()) and len(r.stdout.split()) == 2
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False


def dateizeit(py, tage, ordner):
    """File times follow the moved clock: True at once, or after tools/zeitreise_stat.c was built into ordner and is
    loaded with every run; False when they still do not (no cc, another libc)."""
    if _folgt(py, tage):
        return True
    so = os.path.join(ordner, "zeitreise_stat.so")
    try:
        r = subprocess.run(["cc", "-shared", "-fPIC", "-O2", "-o", so, SHIM, "-ldl"], capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if r.returncode != 0:
        return False
    _shim["so"] = so
    return _folgt(py, tage) and _folgt(py, 0)


def lauf(py, name, tage, frist=FRIST):
    """One module under libfaketime, tage days ahead: "gruen", "rot" or "haengt" (no answer within frist)."""
    env = _umgebung(tage)
    cmd = ["faketime", "-f", f"+{int(tage)}d", py, "-m", "unittest", "discover", "-s", "tests", "-p", name + ".py"]
    # its own process group: faketime starts Python as a child, and a module that hangs must go as a whole
    # (the first full run left a dozen of them running for hours)
    p = subprocess.Popen(cmd, cwd=APP, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True)
    try:
        err = p.communicate(timeout=frist)[1]
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        p.communicate()
        return "haengt", []
    if p.returncode == 0:
        return "gruen", []
    rot = [z.split(" ", 1)[1].strip() for z in err.decode("utf-8", "replace").splitlines()
           if z.startswith(("FAIL: ", "ERROR: "))]
    return "rot", rot


def urteil(vorn, heute):
    """What a module's two runs say: "gruen", "datum" (red ahead, green today: it depends on the date) or
    "gestoert" (red or stuck with today's date too: libfaketime disturbs it)."""
    if vorn == "gruen":
        return "gruen"
    return "datum" if heute == "gruen" else "gestoert"


def pruefe(py, name, tage):
    vorn, rot = lauf(py, name, tage)
    heute = "gruen" if vorn == "gruen" else lauf(py, name, 0)[0]
    return name, urteil(vorn, heute), rot


def main(argv):
    tage, jobs, names = TAGE, JOBS, []
    it = iter(argv)
    for a in it:
        if a == "--tage":
            tage = int(next(it))
        elif a == "-j":
            jobs = int(next(it))
        else:
            names.append(a)
    if not shutil.which("faketime"):
        print("zeitreise: the program faketime is missing (sudo apt-get install faketime)", flush=True)
        return 2
    py = VENV_PY if os.path.exists(VENV_PY) and not os.environ.get("GITHUB_ACTIONS") else sys.executable
    mods = module(names)
    with tempfile.TemporaryDirectory(prefix="zeitreise-") as ordner:
        if not dateizeit(py, tage, ordner):
            print("zeitreise: file times do not follow the moved clock (needs cc for tools/zeitreise_stat.c)", flush=True)
            return 2
        print(f"zeitreise: {len(mods)} modules, clock {tage} days ahead, {jobs} at a time"
              + (", file times by zeitreise_stat" if _shim["so"] else ""), flush=True)
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            out = list(pool.map(lambda n: pruefe(py, n, tage), mods))
    datum = [(n, rot) for n, u, rot in out if u == "datum"]
    gestoert = [n for n, u, _ in out if u == "gestoert"]
    note = os.environ.get("ZEITREISE_NOTE")
    lines = []
    if datum:
        lines += [f"Rot mit der Uhr {tage} Tage voraus, grün mit dem heutigen Datum (hängt vom Datum ab):", ""]
        lines += [f"- `{t}`" for n, rot in datum for t in (rot or [n])]
    if gestoert:
        lines += ["", "Von libfaketime gestört (auch mit heutigem Datum rot oder ohne Antwort; zählt nicht):", ""]
        lines += [f"- `{n}`" for n in gestoert]
    if note:
        with open(note, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    print(f"zeitreise: {len(mods) - len(datum) - len(gestoert)} green | {len(datum)} depend on the date | "
          f"{len(gestoert)} disturbed", flush=True)
    return 1 if datum else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
