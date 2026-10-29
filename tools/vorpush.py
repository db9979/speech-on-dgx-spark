#!/usr/bin/env python3
"""Quick test before a push (guideline part 10 point 5): one command instead of a hand-picked list.

    python3 tools/vorpush.py              checks, regenerates the docs, runs every test module (see 4.)
    python3 tools/vorpush.py --liste      only shows which tests would run
    python3 tools/vorpush.py -j 2         two test modules at the same time (default JOBS)
    python3 tools/vorpush.py --rotfix     the push repairs a red main: the stop in 0. does not hold
    python3 tools/vorpush.py test_live    adds test modules by name

What it does, in this order, and it stops loudly at the first problem:
0. PUSH-STOPP: the newest finished GitHub "Tests" run on main is red (V01.0.820, Dominik 2026-10-19 "1b"; main was
   red 10 h over night and nine pushes landed on it). Only a fix for it passes, with --rotfix. When GitHub cannot
   be asked, it says so and goes on (the full run on GitHub still decides).
1. app/VERSION is higher than on origin/main and is the top line of CHANGELOG.md (bump forgotten or stale).
1b. The system packages GitHub "Tests" installs with apt (the `apt-get install` lines in .github/workflows/tests.yml,
   the one list): a missing one is installed here (apt-get as root, else with `sudo -n`); when that is not possible
   it stops at once with the exact command, never a red test_fernbild in the middle of the run (a cloud container
   without x11vnc, 2026-10-29). A list found complete is remembered (APT_MARK) until the workflow's list changes.
2. A Python 3.11 venv with the panel's pinned packages (app/requirements-panel.lock, like GitHub "Tests") in
   ~/.cache/speech-spark-vorpush; it is rebuilt when the lock file changes. Without fastapi it stops: with the
   system Python `hilfe.py --docs` fails and hilfe_docs.json stays stale (red V01.0.677).
3. `app/panel/hilfe.py --docs` with that venv; files it changed are named so they go into the same commit.
4. The tests: every test module except SLOW (since V01.0.820: picking by file name missed test_mail_zeit and
   test_hilfe_quality, which import the changed module, and main went red for .808-.817). A module in SLOW runs
   when a changed file is one of its own (test_<name>.py, a file it names, or a file under SLOW_WHEN).
   Each module runs as `selftest.py discover -s tests -p test_NAME.py` (a red test gets its second try there).
Exit code 0 only when everything is green. It changes nothing but the generated docs, its own venv and the missing system packages (1b.).
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
TESTS = os.path.join(APP, "tests")
LOCK = os.path.join(APP, "requirements-panel.lock")
VENV = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "speech-spark-vorpush", "venv")
PY = "python3.11"   # the version GitHub "Tests" runs (.github/workflows/tests.yml)
JOBS = 4            # modules at the same time; each runs its own panel in its own state folder
REPO = "db9979/speech-on-dgx-spark"
APT_MARK = os.path.join(os.path.dirname(VENV), "apt-ok")   # sha256 of the package list last found complete
RUNS = "https://api.github.com/repos/%s/actions/workflows/tests.yml/runs?branch=main&event=push&per_page=30"

# the browser test of every page takes more than half of the whole run (tests/dauer.json, ~450 of ~870 s); it runs
# when the pages could have changed: a file under one of SLOW_WHEN or a file it names (tests_for)
SLOW = ("test_ui_browser",)
SLOW_WHEN = ("app/panel/static/", "app/panel/panel.py", "app/panel/guides.py", "app/panel/hilfe.py")

# guard tests that run before every push, whatever changed (the one list; CLAUDE.md and the guideline point here).
# test_hilfe and test_scanner since 2026-10-16: a stale hilfe_docs.json (.677) and a route missing in the
# scanner (.682) turned main red although the changed files' own tests were green.
WAECHTER = ("test_richtlinie", "test_aufraeumen", "test_technik", "test_sperre_ueberall", "test_log_luecken",
            "test_app_gleichstand", "test_sprunglinks", "test_changelog", "test_doku_stand", "test_hilfe",
            "test_scanner", "test_loopwacht")


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)


def stop(text):
    print("vorpush: STOPP " + text, flush=True)
    sys.exit(1)


def version_num(text):
    m = re.fullmatch(r"V(\d+)\.(\d+)\.(\d+)", (text or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def check_version(base):
    mine = open(os.path.join(APP, "VERSION"), encoding="utf-8").read().strip()
    theirs = git("show", base + ":app/VERSION").stdout.strip()
    if version_num(mine) is None:
        stop("app/VERSION " + mine + " is not of the form V01.1.NNN")
    if version_num(theirs) and version_num(mine) <= version_num(theirs):
        stop("app/VERSION " + mine + " is not higher than " + theirs + " on " + base + ": take the next free number")
    top = next((ln for ln in open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") if ln.startswith("- **V")), "")
    if not top.startswith("- **" + mine + "**"):
        stop("the top line of CHANGELOG.md is not " + mine)
    print("vorpush: version " + mine + " (" + base + " " + theirs + ")", flush=True)


def changed_files(base):
    """Files changed against the merge base with base: commits, working tree and new files."""
    mb = git("merge-base", "HEAD", base).stdout.strip() or base
    names = set(git("diff", "--name-only", mb).stdout.split())
    names |= set(git("ls-files", "--others", "--exclude-standard").stdout.split())
    return sorted(n for n in names if n)


def tests_for(files, tests_dir=TESTS):
    """Test module names (without .py) for the changed files: test_<stem>.py, a changed test itself, and every
    test whose source names the file (its base name, e.g. "live.js" or "install.sh")."""
    have = sorted(f[:-3] for f in os.listdir(tests_dir) if f.startswith("test_") and f.endswith(".py"))
    sources = {}
    for t in have:
        with open(os.path.join(tests_dir, t + ".py"), encoding="utf-8") as f:
            sources[t] = f.read()
    out = set()
    for path in files:
        base = os.path.basename(path)
        stem = base.rsplit(".", 1)[0]
        if base.startswith("test_") and base.endswith(".py") and stem in sources:
            out.add(stem)
            continue
        if "test_" + stem in sources:
            out.add("test_" + stem)
        if "." in base and len(base) > 4:   # a bare name like "VERSION" or "x" would match everywhere
            out |= {t for t, s in sources.items() if base in s}
    return sorted(out)


def main_state(runs):
    """update.main_state, the one copy (the panel shows "rot seit" with it); taken from the file alone, so this
    script needs none of the panel's packages."""
    import ast
    path = os.path.join(APP, "panel", "update.py")
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main_state")
    space = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, "exec"), space)
    return space["main_state"](runs)


def check_main(rotfix):
    """Stop 0.: no push onto a red main (PUSH-STOPP), except the fix itself (--rotfix)."""
    try:
        req = urllib.request.Request(RUNS % REPO, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            runs = json.load(r).get("workflow_runs") or []
    except (OSError, ValueError) as e:
        print("vorpush: main state unknown (GitHub not readable: %s), the full run on GitHub decides" % type(e).__name__,
              flush=True)
        return
    state, since = main_state(runs)
    running = any(isinstance(r, dict) and r.get("status") != "completed" for r in runs[:5])
    print("vorpush: main on GitHub " + state + (" since " + since if since else "")
          + (" (a newer run is still going)" if running else ""), flush=True)
    if state == "red" and not rotfix:
        stop("PUSH-STOPP: main is red on GitHub since " + str(since) + ". Only the fix for it is pushed, with "
             "--rotfix; tell the coordinator, it names who fixes it")


def pick(files, extra=(), tests_dir=TESTS):
    """Every test module, SLOW ones only when a changed file is theirs; WAECHTER and extra always."""
    have = sorted(f[:-3] for f in os.listdir(tests_dir) if f.startswith("test_") and f.endswith(".py"))
    own = set(tests_for(files, tests_dir))
    pages = any(f.startswith(SLOW_WHEN) for f in files)
    out = {t for t in have if t not in SLOW or t in own or pages}
    return sorted(out | {w for w in WAECHTER if w in have} | set(extra))


def lock_sum():
    with open(LOCK, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def playwright_pin():
    with open(os.path.join(ROOT, ".github", "workflows", "tests.yml"), encoding="utf-8") as f:
        m = re.search(r"playwright==([\d.]+)", f.read())
    return m.group(1) if m else None


def apt_packages():
    """The packages GitHub "Tests" installs with apt (every `apt-get install` line of the workflow, in order)."""
    with open(os.path.join(ROOT, ".github", "workflows", "tests.yml"), encoding="utf-8") as f:
        text = f.read()
    out = []
    for line in re.findall(r"^\s*(?:sudo )?apt-get install ([^\n#]+)", text, re.M):
        out += [w for w in line.split() if not w.startswith("-") and w not in out]
    return out


def apt_missing(pkgs):
    """The packages of pkgs that no installed package is or provides (Ubuntu 24.04 installs libguac-client-vnc0 as
    libguac-client-vnc0t64, which provides the old name); all of them without dpkg."""
    try:
        r = subprocess.run(["dpkg-query", "-W", "-f=${Status}\t${Package}\t${Provides}\n"], capture_output=True, text=True)
    except OSError:
        return list(pkgs)
    have = set()
    for line in r.stdout.splitlines():
        status, _, rest = line.partition("\t")
        if status.endswith(" installed"):
            name, _, provides = rest.partition("\t")
            have.add(name.split(":")[0])
            have.update(re.sub(r"\(.*?\)", "", x).strip() for x in provides.split(","))
    return [p for p in pkgs if p not in have]


def system_packages():
    """1b.: GitHub's apt packages here too, installed when missing, or a stop with the command before any test."""
    pkgs = apt_packages()
    want = hashlib.sha256(" ".join(pkgs).encode()).hexdigest()
    try:
        with open(APT_MARK) as f:
            if f.read().strip() == want:
                return
    except OSError:
        pass
    missing = apt_missing(pkgs)
    if missing:
        cmd = ["apt-get", "install", "-y", "-q", "--no-install-recommends", *missing]
        hand = "sudo apt-get update && sudo " + " ".join(cmd)
        if subprocess.run(["which", "apt-get"], capture_output=True).returncode:
            stop("system packages missing (" + " ".join(missing) + ") and no apt-get here: install them, on Debian/Ubuntu: " + hand)
        pre = [] if os.geteuid() == 0 else ["sudo", "-n"]
        if pre and subprocess.run(["which", "sudo"], capture_output=True).returncode:
            stop("system packages missing (" + " ".join(missing) + "), not root and no sudo: " + hand)
        print("vorpush: installing system packages like GitHub \"Tests\": " + " ".join(missing), flush=True)
        env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
        if subprocess.run(pre + cmd, env=env).returncode:      # an old package index: update once, then again
            subprocess.run(pre + ["apt-get", "update", "-q"], env=env)
            subprocess.run(pre + cmd, env=env)
        missing = apt_missing(missing)
        if missing:
            stop("system packages could not be installed (" + " ".join(missing) + "): " + hand)
        subprocess.run(pre + ["systemctl", "disable", "--now", "guacd.service"], capture_output=True)   # like GitHub
    os.makedirs(os.path.dirname(APT_MARK), exist_ok=True)
    with open(APT_MARK, "w") as f:
        f.write(want + "\n")


def venv_python(need_browser):
    py = os.path.join(VENV, "bin", "python")
    mark = os.path.join(VENV, ".lock-sha256")
    fresh = os.path.exists(py) and os.path.exists(mark) and open(mark).read().strip() == lock_sum()
    if not fresh:
        if subprocess.run(["which", PY], capture_output=True).returncode:
            stop(PY + " is missing (GitHub \"Tests\" runs 3.11)")
        print("vorpush: building the venv " + VENV + " from app/requirements-panel.lock", flush=True)
        if subprocess.run([PY, "-m", "venv", "--clear", VENV]).returncode:
            stop("venv could not be created")
        r = subprocess.run([py, "-m", "pip", "install", "-q", "--no-deps", "--require-hashes", "-r", LOCK])
        if r.returncode:
            stop("pip could not install app/requirements-panel.lock")
        with open(mark, "w") as f:
            f.write(lock_sum() + "\n")
    if subprocess.run([py, "-c", "import fastapi"], capture_output=True).returncode:
        stop("the venv has no fastapi: delete " + VENV + " and start again")
    if need_browser and subprocess.run([py, "-c", "import playwright"], capture_output=True).returncode:
        pin = playwright_pin()
        if not pin or subprocess.run([py, "-m", "pip", "install", "-q", "playwright==" + pin]).returncode:
            stop("playwright could not be installed (browser tests)")
    return py


def regen_docs(py):
    before = git("status", "--porcelain").stdout
    r = subprocess.run([py, os.path.join("app", "panel", "hilfe.py"), "--docs"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-2000:] + r.stderr[-2000:], flush=True)
        stop("hilfe.py --docs failed: the docs are not current")
    new = sorted(set(git("status", "--porcelain").stdout.splitlines()) - set(before.splitlines()))
    if new:
        print("vorpush: regenerated, commit with it: " + ", ".join(ln[3:] for ln in new), flush=True)
    else:
        print("vorpush: docs current", flush=True)


def run_one(py, name):
    r = subprocess.run([py, "selftest.py", "discover", "-s", "tests", "-p", name + ".py"], cwd=APP,
                       capture_output=True, text=True)
    return name, r.returncode, (r.stdout + r.stderr)[-4000:]


def main(argv):
    jobs, extra, only_list, base, rotfix = JOBS, [], False, "origin/main", False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "-j" and i + 1 < len(argv) and argv[i + 1].isdigit():
            jobs, i = max(1, int(argv[i + 1])), i + 1
        elif a == "--liste":
            only_list = True
        elif a == "--rotfix":
            rotfix = True
        elif a == "--basis" and i + 1 < len(argv):
            base, i = argv[i + 1], i + 1
        elif re.fullmatch(r"test_\w+", a) and os.path.exists(os.path.join(TESTS, a + ".py")):
            extra.append(a)
        else:
            print(__doc__)
            return 2
        i += 1
    if base == "origin/main" and git("fetch", "-q", "origin", "main").returncode:
        stop("git fetch origin main failed: without it the version check would compare against an old main")
    if base == "origin/main" and not only_list:
        check_main(rotfix)
    files = changed_files(base)
    names = pick(files, extra)
    print("vorpush: %d changed files, %d test modules: %s" % (len(files), len(names), " ".join(names)), flush=True)
    if only_list:
        return 0
    check_version(base)
    system_packages()
    py = venv_python(True)   # many modules besides test_ui_browser open pages in Chromium
    regen_docs(py)
    red = []
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        for name, code, tail in pool.map(lambda n: run_one(py, n), names):
            print("vorpush: %s %s" % ("green" if code == 0 else "RED", name), flush=True)
            if code:
                red.append(name)
                print(tail, flush=True)
    if red:
        stop("red: " + " ".join(red) + " (do not push; fix or take the line out of the queue)")
    print("vorpush: all green, %d modules" % len(names), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
