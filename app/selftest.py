"""The self-tests with one second try for the tests that failed (Dominik 2026-10-11, choice 1).

    python selftest.py discover -s tests [-t .]      (GitHub "Tests" and install.sh/update.sh on the Spark)
    python selftest.py tests.test_rauchtest           (named tests, like `python -m unittest`)

Runs the tests like `python -m unittest`. When a few of them fail, exactly those run once more in a fresh process.
- a test that fails twice keeps the run red (exit 1);
- a test that only passes the second time does not block the update, but it never goes unseen: a line
  "WARNUNG erst im zweiten Versuch grün: <test>" in the log, a GitHub warning and a line in the run's summary;
- more than MAX_RETRY failures are not a wobble but a real break: no second try, red at once.
Nothing is skipped and no test changes: the second try runs the very same test.

    python selftest.py discover -s tests --part 2/4    (GitHub "Tests": four parts at the same time, V01.0.502)
    python selftest.py --sum <folder> 4                 (GitHub "Tests", job "Ergebnis": the parts together)

With --part K/N only the K-th of N parts runs. The parts are cut from the same discovery by test module (a class
with entries per test in tests/dauer.json test by test), so together they hold every test exactly once (parts()).
The durations in tests/dauer.json only decide which part a unit goes to; one missing there counts NEW_UNIT
seconds. Each part writes what failed the first time to $SELFTEST_REPORT; --sum adds the parts up, so the rule
"more than MAX_RETRY failures is red" holds for the whole run, not per part. With $SELFTEST_NOTE --sum also writes
which tests stayed red and which passed only the second time; GitHub opens the issue "main rot" with it (closed
again by the next green run) and counts the wobbly ones on the issue "Wackelnde Tests" (V01.0.820).
"""
import json
import os
import re
import subprocess
import sys
import time
import unittest

MAX_RETRY = 5          # more failures than this: something is really broken, no second try
WARN = "WARNUNG erst im zweiten Versuch grün"
NEW_UNIT = 10          # seconds a unit not yet in tests/dauer.json counts for when the parts are cut


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


def _key(tid, split=()):
    """The unit a test belongs to: its module ("test_x"), or the test itself ("test_x.Class.test") for a class in
    split. Whole modules, because some tests count on what an earlier class of their module left behind; a module
    that did not import (unittest's _FailedTest) is a unit under its module name too."""
    if tid.startswith("unittest.loader._FailedTest."):
        return tid.rsplit(".", 1)[1]
    cls = tid.rsplit(".", 1)[0]
    return tid if cls in split else cls.split(".", 1)[0]


def _units(suite, split=()):
    """The units of a discovery in their order: [(key, suite of its tests)]."""
    units, index = [], {}

    def walk(s):
        for t in s:
            if isinstance(t, unittest.TestSuite):
                walk(t)
                continue
            key = _key(t.id(), split)
            if key not in index:
                index[key] = unittest.TestSuite()
                units.append((key, index[key]))
            index[key].addTest(t)
    walk(suite)
    return units


def _durations(top):
    try:
        with open(os.path.join(top, "dauer.json"), encoding="utf-8") as f:
            return {k: float(v) for k, v in json.load(f).items()}
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def _split(durations):
    """Classes cut test by test: those with "module.Class.test" entries in dauer.json (one class alone would
    otherwise be longer than a whole part, like the browser test). Each part starts such a class anew; the rest of
    its module stays one unit."""
    return {k.rsplit(".", 1)[0] for k in durations if k.count(".") == 2}


def parts(keys, n, durations):
    """Cuts the classes into n parts of about the same duration (longest first onto the shortest part).
    Every key lands in exactly one part, and the cut depends only on the names and durations, so all parts
    running at the same time agree on it."""
    load, out = [0.0] * n, [[] for _ in range(n)]
    for key in sorted(keys, key=lambda k: (-durations.get(k, NEW_UNIT), k)):
        i = min(range(n), key=lambda j: (load[j], j))
        out[i].append(key)
        load[i] += durations.get(key, NEW_UNIT)
    return out


class _Timed(unittest.TextTestResult):
    """Notes how long each unit took, its setUpClass included (time from the end of the test before)."""
    split = ()

    def startTestRun(self):
        super().startTestRun()
        self.durations, self._last = {}, time.monotonic()

    def stopTest(self, test):
        super().stopTest(test)
        now = time.monotonic()
        key = _key(test.id(), self.split)
        self.durations[key] = self.durations.get(key, 0.0) + now - self._last
        self._last = now


def _report(names, result, red=None):
    """$SELFTEST_REPORT: what failed the first time, what stayed red (red; until the second try ran, the same) and
    what passed only the second time (wobbly), for --sum and the note on GitHub."""
    path = os.environ.get("SELFTEST_REPORT")
    if not path:
        return
    dur = {k: round(v, 1) for k, v in getattr(result, "durations", {}).items()}
    red = names if red is None else red
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"failed_first": names, "red": red, "wobbly": [n for n in names if n not in red],
                   "ran": result.testsRun, "dauer": dur}, f)


def run_part(argv, k, n):
    """Runs part k of n of the discovery in argv; returns the result like unittest.main."""
    start, top = "tests", None
    for i, a in enumerate(argv):
        if a in ("-s", "--start-directory") and i + 1 < len(argv):
            start = argv[i + 1]
        if a in ("-t", "--top-level-directory") and i + 1 < len(argv):
            top = argv[i + 1]
    suite = unittest.defaultTestLoader.discover(start, top_level_dir=top)
    durations = _durations(os.path.abspath(start))
    split = _split(durations)
    units = _units(suite, split)
    mine = set(parts([key for key, _ in units], n, durations)[k - 1])
    print(f"selftest: part {k}/{n}: {len(mine)} of {len(units)} units", flush=True)
    timed = type("Timed", (_Timed,), {"split": split})
    # in the order of the discovery, as in one whole run
    return unittest.TextTestRunner(resultclass=timed).run(unittest.TestSuite(s for key, s in units if key in mine))


def total(folder, n):
    """Job "Ergebnis": every part reported, and all together had not more than MAX_RETRY first failures."""
    names, ran, dur, red, wobbly = [], 0, {}, [], []
    for k in range(1, n + 1):
        path = os.path.join(folder, f"teil-{k}", "teil.json")
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            print(f"selftest: part {k}/{n} sent no result", flush=True)
            return 1
        names += [str(x) for x in data.get("failed_first", [])]
        red += [str(x) for x in data.get("red", data.get("failed_first", []))]
        wobbly += [str(x) for x in data.get("wobbly", [])]
        ran += int(data.get("ran", 0))
        part = {str(c): float(v) for c, v in (data.get("dauer") or {}).items()}
        dur.update(part)
        print(f"selftest: part {k}/{n} took {sum(part.values()):.0f} s for {data.get('ran', 0)} tests", flush=True)
    print(f"selftest: {ran} tests in {n} parts, {len(names)} failed the first time", flush=True)
    out = os.environ.get("SELFTEST_DAUER")
    if out and dur:
        # measured on GitHub: copied to tests/dauer.json when the parts drift apart
        with open(out, "w", encoding="utf-8") as f:
            json.dump(dict(sorted(dur.items())), f, indent=0, ensure_ascii=False)
            f.write("\n")
    _note(red if len(names) <= MAX_RETRY else names, wobbly)
    if ran <= 0:
        return 1
    if len(names) > MAX_RETRY:
        print(f"selftest: {len(names)} failed, more than {MAX_RETRY} is a real break: {' '.join(names)}", flush=True)
        return 1
    return 0


def _note(red, wobbly):
    """$SELFTEST_NOTE (GitHub "Tests", job "Ergebnis"): the text of the issue "main rot" or of the comment on
    "Wackelnde Tests", test names only (V01.0.820). Red first; nothing written when all is green and steady."""
    out = os.environ.get("SELFTEST_NOTE")
    if not out or not (red or wobbly):
        return
    lines = []
    if red:
        lines += ["Rot (auch im zweiten Versuch oder mehr als %d auf einmal):" % MAX_RETRY, ""]
        lines += ["- `%s`" % x for x in red[:40]] + (["- und %d weitere" % (len(red) - 40)] if len(red) > 40 else [])
    if wobbly:
        lines += ([""] if lines else []) + [WARN + ":", ""] + ["- `%s`" % x for x in wobbly[:40]]
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def rerun(top, names):
    """The second try, in this (fresh) process: True when every named test passes."""
    sys.path.insert(0, top)
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return result.wasSuccessful()


def main(argv):
    if argv[:1] == ["--rerun"]:
        return 0 if rerun(argv[1], argv[2:]) else 1
    if argv[:1] == ["--sum"]:
        return total(argv[1], int(argv[2]))
    part = None
    if "--part" in argv:
        i = argv.index("--part")
        m = re.fullmatch(r"(\d+)/(\d+)", argv[i + 1] if i + 1 < len(argv) else "")
        if not m or not 1 <= int(m.group(1)) <= int(m.group(2)) or argv[:1] != ["discover"]:
            print("selftest: --part K/N needs 1 <= K <= N and discover", flush=True)
            return 2
        part = (int(m.group(1)), int(m.group(2)))
        argv = argv[:i] + argv[i + 2:]
    if part:
        result = run_part(argv, *part)
    else:
        result = unittest.main(module=None, argv=["selftest"] + argv, exit=False).result
    names = [] if result.wasSuccessful() else failed_names(result)
    _report(names, result)
    if result.wasSuccessful():
        return 0
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
    _report(names, result, red=[])
    lines = [f"{WARN}: {n}" for n in names]
    for line in lines:
        print(line, flush=True)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::warning title=Wackelnder Test::{line}", flush=True)
    _summary(lines)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
