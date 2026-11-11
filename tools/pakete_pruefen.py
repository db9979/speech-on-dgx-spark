#!/usr/bin/env python3
"""Pakete prüfen: the pinned Python packages against the OSV database (code review 2026-11-11, Dominik „1-11“).

    python3 tools/pakete_pruefen.py            every app/requirements-*.lock

The Spark does this itself (Zustand → System-Updates, panel/systemupdates.check_osv); this is the same question
from GitHub, every night (.github/workflows/pakete.yml), so a known hole in a pinned package is seen even when no
Spark looked: the issue „Pakete mit bekannter Lücke“ names package, version and the ids. Only names and versions
of public packages go out, only ids come back. Not a step of "Tests" on purpose: a hole published tonight would
turn main red without any push, and the Spark installs only versions whose "Tests" run is green.

Exit code 0: no known hole; 1: holes (named, written to $PAKETE_NOTE); 2: no answer (no verdict, nothing written).
"""
import glob
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OSV_URL = "https://api.osv.dev/v1/querybatch"       # as panel/systemupdates.OSV_URL (test_pakete_pruefen)
OSV_MAX = 2 * 1048576
OSV_ID = re.compile(r"[A-Z][A-Za-z0-9\-]{2,40}")
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._\-]{0,63})==([A-Za-z0-9.+!\-]{1,40})\s")     # as systemupdates.LOCK_LINE
MAX_IDS = 5


def gepinnt(root=ROOT):
    """{name: version} of every app/requirements-*.lock."""
    out = {}
    for path in sorted(glob.glob(os.path.join(root, "app", "requirements-*.lock"))):
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = PIN.match(line)
                if m:
                    out[m.group(1).lower()] = m.group(2)
    return dict(sorted(out.items()))


def frage(pak, post=None):
    """{name: {"v": version, "ids": [...]}} for the packages OSV knows a hole in; raises when there is no answer."""
    body = json.dumps({"queries": [{"package": {"name": n, "ecosystem": "PyPI"}, "version": v}
                                   for n, v in pak.items()]}).encode()
    if post is None:
        def post(data):
            req = urllib.request.Request(OSV_URL, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:      # noqa: S310  (fixed https address)
                return r.read(OSV_MAX + 1)
    raw = post(body)
    if len(raw) > OSV_MAX:
        raise ValueError("answer too long")
    res = (json.loads(raw) or {}).get("results")
    if not isinstance(res, list) or len(res) != len(pak):
        raise ValueError("answer does not fit the question")
    warn = {}
    for (n, v), x in zip(pak.items(), res):
        ids = [str(y.get("id")) for y in (x or {}).get("vulns") or []
               if isinstance(y, dict) and OSV_ID.fullmatch(str(y.get("id")))]
        if ids:
            warn[n] = {"v": v, "ids": ids[:MAX_IDS]}
    return warn


def main(argv, post=None):
    pak = gepinnt()
    if not pak:
        print("pakete: no pinned package found", flush=True)
        return 2
    try:
        warn = frage(pak, post)
    except Exception as e:   # noqa: BLE001  (no network, another answer: no verdict)
        print(f"pakete: osv fehler {type(e).__name__} | {len(pak)} pakete", flush=True)
        return 2
    print(f"pakete: osv ok {len(warn)} warnungen {len(pak)} pakete", flush=True)
    if not warn:
        return 0
    lines = ["Gepinnte Python-Pakete mit bekannter Lücke (OSV):", ""]
    lines += [f"- `{n}` {w['v']}: {', '.join(w['ids'])}" for n, w in sorted(warn.items())]
    print("\n".join(lines), flush=True)
    note = os.environ.get("PAKETE_NOTE")
    if note:
        with open(note, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
