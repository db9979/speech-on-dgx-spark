"""The self-tests with one second try for the tests that failed (Dominik 2026-10-11, choice 1).

    python selftest.py discover -s tests [-t .]      (GitHub "Tests" and install.sh/update.sh on the Spark)
    python selftest.py tests.test_rauchtest           (named tests, like `python -m unittest`)

Runs the tests like `python -m unittest`. When a few of them fail, exactly those run once more in a fresh process.
- a test that fails twice keeps the run red (exit 1);
- a test that only passes the second time does not block the update, but it never goes unseen: a line
  "WARNUNG erst im zweiten Versuch grün: <test>" in the log, a GitHub warning and a line in the run's summary;
- more than MAX_RETRY failures are not a wobble but a real break: no second try, red at once.
Nothing is skipped and no test changes: the second try runs the very same test.
"""
import os
import re
import subprocess
import sys
import unittest

MAX_RETRY = 5          # more failures than this: something is really broken, no second try
WARN = "WARNUNG erst im zweiten Versuch grün"


def _top(argv):
    """The folder the test names are relative to (what unittest puts on sys.path)."""
    if argv[:1] == ["discover"]:
        start, top = "tests", None
        for i, a in enumerate(argv):
            if a in ("-s", "--start-directory") and i + 1 < len(argv):
                start = argv[i + 1]
            if a in ("-t", "--top-level-directory") and i + 1 < len(argv):
                top = argv[i + 1]
        return os.path.abspath(top or start)
    return os.getcwd()


def _name(test):
    """The name to load the failed test again: a test id, or for a failed setUpClass/setUpModule/import its class
    or module ("setUpClass (tests.x.Class)" -> "tests.x.Class")."""
    tid = test.id()
    m = re.match(r"^(?:setUpClass|tearDownClass|setUpModule|tearDownModule) \((.+)\)$", tid)
    if m:
        return m.group(1)
    if tid.startswith("unittest.loader._FailedTest."):
        return tid.rsplit(".", 1)[1]
    return tid


def failed_names(result):
    seen = []
    for test, _ in result.failures + result.errors + [(t, "") for t in getattr(result, "unexpectedSuccesses", [])]:
        n = _name(test)
        if n not in seen:
            seen.append(n)
    return seen


def _summary(lines):
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write("".join(f"- ⚠️ {line}\n" for line in lines))
    except OSError:
        pass


def rerun(top, names):
    """The second try, in this (fresh) process: True when every named test passes."""
    sys.path.insert(0, top)
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return result.wasSuccessful()


def main(argv):
    if argv[:1] == ["--rerun"]:
        return 0 if rerun(argv[1], argv[2:]) else 1
    prog = unittest.main(module=None, argv=["selftest"] + argv, exit=False)
    result = prog.result
    if result.wasSuccessful():
        return 0
    names = failed_names(result)
    if not names or len(names) > MAX_RETRY:
        print(f"\nselftest: {len(names)} failed, no second try (more than {MAX_RETRY} is a real break)", flush=True)
        return 1
    print(f"\nselftest: second try for {len(names)}: {' '.join(names)}", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()
    again = subprocess.run([sys.executable, os.path.abspath(__file__), "--rerun", _top(argv)] + names)
    if again.returncode != 0:
        print(f"selftest: failed twice: {' '.join(names)}", flush=True)
        return 1
    lines = [f"{WARN}: {n}" for n in names]
    for line in lines:
        print(line, flush=True)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::warning title=Wackelnder Test::{line}", flush=True)
    _summary(lines)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
