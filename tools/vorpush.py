#!/usr/bin/env python3
"""Quick test before a push (guideline part 10 point 5): one command instead of a hand-picked list.

    python3 tools/vorpush.py              checks, regenerates the docs, runs the affected and the guard tests
    python3 tools/vorpush.py --liste      only shows which tests would run
    python3 tools/vorpush.py -j 3         three test modules at the same time
    python3 tools/vorpush.py test_live    adds test modules by name

What it does, in this order, and it stops loudly at the first problem:
1. app/VERSION is higher than on origin/main and is the top line of CHANGELOG.md (bump forgotten or stale).
2. A Python 3.11 venv with the panel's pinned packages (app/requirements-panel.lock, like GitHub "Tests") in
   ~/.cache/speech-spark-vorpush; it is rebuilt when the lock file changes. Without fastapi it stops: with the
   system Python `hilfe.py --docs` fails and hilfe_docs.json stays stale (red V01.0.677).
3. `app/panel/hilfe.py --docs` with that venv; files it changed are named so they go into the same commit.
4. The tests: per changed file test_<name>.py and every test that names the file (e.g. "live.js"), plus WAECHTER.
   Each module runs as `selftest.py discover -s tests -p test_NAME.py` (a red test gets its second try there).
Exit code 0 only when everything is green. It changes nothing but the generated docs and its own venv.
"""
import hashlib
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
TESTS = os.path.join(APP, "tests")
LOCK = os.path.join(APP, "requirements-panel.lock")
VENV = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "speech-spark-vorpush", "venv")
PY = "python3.11"   # the version GitHub "Tests" runs (.github/workflows/tests.yml)

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
        stop("app/VERSION " + mine + " is not of the form V01.0.NNN")
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


def lock_sum():
    with open(LOCK, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def playwright_pin():
    with open(os.path.join(ROOT, ".github", "workflows", "tests.yml"), encoding="utf-8") as f:
        m = re.search(r"playwright==([\d.]+)", f.read())
    return m.group(1) if m else None


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
    jobs, extra, only_list, base = 1, [], False, "origin/main"
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "-j" and i + 1 < len(argv) and argv[i + 1].isdigit():
            jobs, i = max(1, int(argv[i + 1])), i + 1
        elif a == "--liste":
            only_list = True
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
    files = changed_files(base)
    names = sorted(set(tests_for(files)) | set(WAECHTER) | set(extra))
    print("vorpush: %d changed files, %d test modules: %s" % (len(files), len(names), " ".join(names)), flush=True)
    if only_list:
        return 0
    check_version(base)
    py = venv_python("test_ui_browser" in names)
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
