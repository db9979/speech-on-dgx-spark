#!/usr/bin/env python3
"""Lücke schließen (Weg 1, Dominik 2026-11-13 „1“): a panel package with a known hole and a fixed version is raised
to that version without Claude, by fixed rules, and comes to the Spark with the next update.

    python3 tools/luecke_schliessen.py anheben [--heute YYYY-MM-DD]
        on this checkout: asks OSV (tools/pakete_pruefen.py), raises every package of app/requirements-panel.lock
        whose holes have a fix with uv to that version (nothing else moves), sets the next version in app/VERSION and
        one line in CHANGELOG.md and both READMEs. Exit 0: changed (names written to $LUECKE_NOTE);
        3: nothing to raise; 2: no answer from OSV or uv failed (nothing changed).
    python3 tools/luecke_schliessen.py gleich <ref>
        exit 0 when app/requirements-panel.lock here is the same as in <ref> (the branch whose "Tests" passed).

Only the panel's lock file is raised: its packages are what GitHub's "Tests" really run. vLLM and vllm-omni (install.sh),
yt-dlp (its own lock with ytquelle.VERSION) and the Docker images stay with a person or a Claude thread: GitHub's
tests do not start them, so a green run would say nothing about them. The workflow .github/workflows/luecke-schliessen.yml
runs this only when the repository variable LUECKEN_SCHLIESSEN is "an" (off until Dominik sets it): on the branch
luecke/auto first, then "Tests" on that branch, and only after a green run again on the newest main, pushed when the
lock file is exactly the tested one.
"""
import datetime
import importlib.util
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
LOCK = "requirements-panel.lock"
# the command in the lock file's head (requirements-panel.in names it); only --exclude-newer moves, to the day after
# heute, so a fix published today is seen; --upgrade-package lets only the raised packages move
UV = ["uv", "pip", "compile", "--universal", "--generate-hashes", "--python-version", "3.11",
      "--override", "requirements-panel.override", "requirements-panel.in", "-o", LOCK, "--quiet"]
VERSION = re.compile(r"^V(\d{2})\.(\d)\.(\d{3})$")
README = {"README.de.md": "## Letzte Änderungen", "README.md": "## Latest changes"}
README_LINES = 10


def pruefer():
    spec = importlib.util.spec_from_file_location("pakete_pruefen", os.path.join(ROOT, "tools", "pakete_pruefen.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def pins(path):
    """{name: version} of one lock file."""
    t = pruefer()
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = t.PIN.match(line)
            if m:
                out[m.group(1).lower()] = m.group(2)
    return out


def ziele(warn):
    """{name: version} to raise: every package with a fixed version (holes without a fix stay named, not raised)."""
    return {n: w["behoben"] for n, w in sorted(warn.items()) if w.get("behoben") and " " not in n}


def naechste(v):
    """The next version after v (V01.0.999 -> V01.1.000)."""
    m = VERSION.match(v.strip())
    if not m:
        raise ValueError("app/VERSION has an unknown form")
    a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3)) + 1
    if c > 999:
        b, c = b + 1, 0
    return f"V{a:02d}.{b}.{c:03d}"


def zeile(raised, sprache):
    teile = ", ".join(f"{n} {alt} → {neu}" for n, (alt, neu) in sorted(raised.items()))
    return (f"Sicherheits-Update ohne Claude: {teile} (bekannte Lücke laut OSV geschlossen)" if sprache == "de" else
            f"Security update without Claude: {teile} (known hole according to OSV closed)")


def buchen(root, raised, heute):
    """New version in app/VERSION, one line at the top of CHANGELOG.md and of both READMEs (oldest line out)."""
    vp = os.path.join(root, "app", "VERSION")
    with open(vp, encoding="utf-8") as f:
        neu = naechste(f.read())
    with open(vp, "w", encoding="utf-8") as f:
        f.write(neu + "\n")
    cp = os.path.join(root, "CHANGELOG.md")
    with open(cp, encoding="utf-8") as f:
        lines = f.read().split("\n")
    first = next(i for i, x in enumerate(lines) if x.startswith("- **V"))
    lines.insert(first, f"- **{neu}** · {heute.isoformat()} · {zeile(raised, 'de')}")
    with open(cp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    for name, head in README.items():
        rp = os.path.join(root, name)
        with open(rp, encoding="utf-8") as f:
            lines = f.read().split("\n")
        start = lines.index(head)
        first = next(i for i in range(start, len(lines)) if lines[i].startswith("- **V"))
        lines.insert(first, f"- **{neu}** {zeile(raised, 'de' if name.endswith('.de.md') else 'en')}")
        last = first
        while last + 1 < len(lines) and lines[last + 1].startswith("- **V"):
            last += 1
        del lines[first + README_LINES:last + 1]
        with open(rp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    return neu


def anheben(root=ROOT, heute=None, post=None, get=None, run=subprocess.run):
    t = pruefer()
    heute = heute or datetime.date.today()
    lock = os.path.join(root, "app", LOCK)
    vorher = pins(lock)
    try:
        warn = t.genauer(t.frage(vorher, post), get)
    except Exception as e:   # noqa: BLE001  (no answer: no verdict, nothing changed)
        print(f"luecke: osv fehler {type(e).__name__}", flush=True)
        return 2, {}
    ziel = ziele(warn)
    if not ziel:
        print(f"luecke: nichts {len(warn)} warnungen 0 behebbar", flush=True)
        return 3, {}
    with open(lock, encoding="utf-8") as f:
        alt_text = f.read()
    cmd = UV + ["--exclude-newer", (heute + datetime.timedelta(days=1)).isoformat()]
    for n, v in ziel.items():
        cmd += ["--upgrade-package", f"{n}>={v}"]
    r = run(cmd, cwd=os.path.join(root, "app"), capture_output=True, text=True, timeout=900)
    nachher = pins(lock) if r.returncode == 0 else {}
    raised = {n: (vorher[n], nachher.get(n, "")) for n in ziel}
    zu_niedrig = [n for n, v in ziel.items() if t.vkey(nachher.get(n)) is None or t.vkey(nachher[n]) < t.vkey(v)]
    if r.returncode != 0 or zu_niedrig:
        with open(lock, "w", encoding="utf-8") as f:
            f.write(alt_text)
        print(f"luecke: uv fehler {r.returncode} {len(zu_niedrig)} nicht erreicht", flush=True)
        return 2, {}
    neu = buchen(root, raised, heute)
    print(f"luecke: angehoben {len(raised)} pakete {neu}", flush=True)
    note = os.environ.get("LUECKE_NOTE")
    if note:
        with open(note, "w", encoding="utf-8") as f:
            f.write(f"{neu} " + zeile(raised, "de") + "\n")
    return 0, raised


def gleich(ref, root=ROOT, run=subprocess.run):
    """Whether the lock file here is the one of ref (byte for byte)."""
    r = run(["git", "show", f"{ref}:app/{LOCK}"], cwd=root, capture_output=True, timeout=60)
    with open(os.path.join(root, "app", LOCK), "rb") as f:
        same = r.returncode == 0 and r.stdout == f.read()
    print(f"luecke: {'gleich' if same else 'anders'}", flush=True)
    return 0 if same else 1


def main(argv):
    if argv[:1] == ["anheben"]:
        heute = None
        if argv[1:2] == ["--heute"] and len(argv) > 2:
            heute = datetime.date.fromisoformat(argv[2])
        return anheben(heute=heute)[0]
    if argv[:1] == ["gleich"] and len(argv) == 2 and re.fullmatch(r"[A-Za-z0-9_./-]{1,100}", argv[1]):
        return gleich(argv[1])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
