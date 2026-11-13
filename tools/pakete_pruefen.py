#!/usr/bin/env python3
"""Pakete prüfen: the pinned Python packages against the OSV database (code review 2026-11-11, Dominik „1-11“).

    python3 tools/pakete_pruefen.py            every app/requirements-*.lock, the engines in install.sh, Docker images

The Spark does this itself (Zustand → System-Updates, panel/systemupdates.check_osv); this is the same question
from GitHub, every night (.github/workflows/pakete.yml), so a known hole in a pinned package is seen even when no
Spark looked: the issue „Pakete mit bekannter Lücke“ names package, version and the ids. Only names and versions
of public packages go out, only ids come back. Not a step of "Tests" on purpose: a hole published tonight would
turn main red without any push, and the Spark installs only versions whose "Tests" run is green.

Since 2026-11-12 (Stand der Technik, Dominik "ok") also the model computer: vLLM and vllm-omni are pinned in
install.sh (VLLM_VERSION, VLLM_OMNI_VERSION, VLLM_LLM_VERSION), not in a lock file, and were seen by nobody. A Docker
image of a model engine (modelle.DOCKER) has no OSV entry; it carries the day it was pinned ("seit") and is named
when it is older than DOCKER_TAGE days, so somebody looks for a newer digest.

Since 2026-11-13 (Schwachstellen, Dominik „1“) every hole also gets its weight and the version that closes it: one more
question per id to OSV (only the id goes out), the CVSS 3 vector computed here or GitHub's own word for it, and the
lowest "fixed" event above the pinned version. $PAKETE_JSON receives the same as data for tools/luecke_schliessen.py,
which raises a panel package to that version by itself (Weg 1, .github/workflows/luecke-schliessen.yml).

Exit code 0: nothing to say; 1: holes or old images (named, written to $PAKETE_NOTE); 2: no answer from OSV (no
verdict, nothing written).
"""
import datetime
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
ALLE_IDS = 30                                        # ids asked for weight and fix per package
VULN_URL = "https://api.osv.dev/v1/vulns/"           # + one id: weight and fixed versions of one hole
VULN_MAX = 1048576
# the weight of a hole, worst first (as the Spark's page shows it); GitHub's own words map onto it
STUFEN = ("kritisch", "hoch", "mittel", "niedrig", "unbekannt")
GHSA_STUFE = {"CRITICAL": "kritisch", "HIGH": "hoch", "MODERATE": "mittel", "MEDIUM": "mittel", "LOW": "niedrig"}
VERSION = re.compile(r"^v?(\d+(?:\.\d+)*)(?:[-_.]?(a|b|c|rc|alpha|beta)[-_.]?(\d*))?(?:[-_.]?post[-_.]?(\d*))?"
                     r"(?:[-_.]?dev[-_.]?(\d*))?(?:\+[A-Za-z0-9.]+)?$", re.I)
# install.sh: the engines' versions (one line each, as install.sh reads them); the name on PyPI
ENGINE = re.compile(r"^(VLLM|VLLM_OMNI|VLLM_LLM)_VERSION=([0-9][0-9A-Za-z.+!\-]{0,39})$", re.M)
ENGINE_NAME = {"VLLM": "vllm", "VLLM_OMNI": "vllm-omni", "VLLM_LLM": "vllm"}
# modelle.py DOCKER: "image": "<name>@sha256:<64 hex>", and on the next line "seit": "YYYY-MM-DD"
DOCKER = re.compile(r'"image":\s*"([a-z0-9][a-z0-9._/-]{0,127})@sha256:[0-9a-f]{64}",\s*\n\s*"seit":\s*"(\d{4}-\d{2}-\d{2})"')
DOCKER_TAGE = 90


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


def motoren(root=ROOT):
    """{name: version} of the engines pinned in install.sh. A second vLLM with another version than VLLM_VERSION
    is asked as "vllm <version>" (the name sent to OSV is the first word)."""
    with open(os.path.join(root, "install.sh"), encoding="utf-8") as f:
        text = f.read()
    out = {}
    for var, ver in ENGINE.findall(text):
        name = ENGINE_NAME[var]
        if out.get(name, ver) != ver:
            name = f"{name} {ver}"
        out[name] = ver
    return out


def abbilder(root=ROOT):
    """[(image, day pinned)] of the model engines' Docker images (modelle.DOCKER)."""
    with open(os.path.join(root, "app", "modelle.py"), encoding="utf-8") as f:
        return [(name, datetime.date.fromisoformat(day)) for name, day in DOCKER.findall(f.read())]


def alt(bilder, heute):
    """[(image, days)] pinned longer ago than DOCKER_TAGE days."""
    return [(n, (heute - d).days) for n, d in bilder if (heute - d).days > DOCKER_TAGE]


def frage(pak, post=None):
    """{name: {"v": version, "ids": [...]}} for the packages OSV knows a hole in; raises when there is no answer."""
    body = json.dumps({"queries": [{"package": {"name": n.split(" ")[0], "ecosystem": "PyPI"}, "version": v}
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
            warn[n] = {"v": v, "ids": ids[:MAX_IDS], "alle": ids[:ALLE_IDS]}
    return warn


def vkey(v):
    """A sortable key for a PEP 440 version (release, pre, post, dev; local part ignored), None when it is no such
    version. The Spark has no packaging library on GitHub's plain python3, so it is done here."""
    m = VERSION.match(str(v or "").strip())
    if not m:
        return None
    rel = tuple(int(x) for x in m.group(1).split("."))
    rel = rel + (0,) * (8 - len(rel)) if len(rel) < 8 else rel
    pre = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "c": 2, "rc": 2}.get((m.group(2) or "").lower())
    dev = m.group(5) is not None
    post = int(m.group(4) or 0) if m.group(4) is not None else -1
    if pre is None:
        pre_key = (-1, 0) if dev and post < 0 else (3, 0)      # 1.0.dev1 < 1.0a1 < 1.0rc1 < 1.0
    else:
        pre_key = (pre, int(m.group(3) or 0))
    return rel + pre_key + (post, 0 if dev else 1, int(m.group(5) or 0) if dev else 0)


def cvss3(vector):
    """The base score of a CVSS 3.0/3.1 vector (FIRST's formula), None for anything else."""
    m = dict(x.split(":", 1) for x in str(vector or "").split("/")[1:] if ":" in x)
    if not str(vector or "").startswith("CVSS:3"):
        return None
    try:
        changed = m["S"] == "C"
        av = {"N": .85, "A": .62, "L": .55, "P": .2}[m["AV"]]
        ac = {"L": .77, "H": .44}[m["AC"]]
        pr = {"N": .85, "L": .68 if changed else .62, "H": .5 if changed else .27}[m["PR"]]
        ui = {"N": .85, "R": .62}[m["UI"]]
        c, i, a = ({"H": .56, "L": .22, "N": 0}[m[k]] for k in ("C", "I", "A"))
    except KeyError:
        return None
    iss = 1 - (1 - c) * (1 - i) * (1 - a)
    impact = 7.52 * (iss - .029) - 3.25 * (iss - .02) ** 15 if changed else 6.42 * iss
    if impact <= 0:
        return 0.0
    base = min((1.08 if changed else 1) * (impact + 8.22 * av * ac * pr * ui), 10)
    n = round(base * 100000)                                       # Roundup of CVSS 3.1
    return n / 100000 if n % 10000 == 0 else (n // 10000 + 1) / 10


def stufe_von(score):
    if score is None:
        return "unbekannt"
    return "kritisch" if score >= 9 else "hoch" if score >= 7 else "mittel" if score >= 4 else "niedrig"


def norm(name):
    return re.sub(r"[-_.]+", "-", str(name or "")).lower()


def einzeln(vuln, name, ver):
    """(stufe, score, fix) of one OSV record for package name at version ver: fix is the lowest "fixed" above ver
    (None when OSV names none)."""
    score = None
    for s in vuln.get("severity") or []:
        if isinstance(s, dict) and str(s.get("type", "")).startswith("CVSS_V3"):
            x = cvss3(s.get("score"))
            if x is not None:
                score = x if score is None else max(score, x)
    stufe = stufe_von(score)
    if score is None:
        stufe = GHSA_STUFE.get(str((vuln.get("database_specific") or {}).get("severity", "")).upper(), "unbekannt")
    have, fixes = vkey(ver), []
    for aff in vuln.get("affected") or []:
        pkg = (aff or {}).get("package") or {}
        if pkg.get("ecosystem") != "PyPI" or norm(pkg.get("name")) != norm(name):
            continue
        for rng in aff.get("ranges") or []:
            for ev in (rng or {}).get("events") or []:
                k = vkey((ev or {}).get("fixed"))
                if k is not None and have is not None and k > have:
                    fixes.append((k, str(ev["fixed"])))
    return stufe, score, (min(fixes)[1] if fixes else None)


def genauer(warn, get=None):
    """Adds to every package in warn: "stufe" (worst), "score", "behoben" (the version closing every hole that has
    a fix) and "ohne_fix" (holes OSV names no fix for). A missing answer leaves "unbekannt" and no fix."""
    if get is None:
        def get(vid):
            with urllib.request.urlopen(VULN_URL + vid, timeout=30) as r:   # noqa: S310  (fixed https address)
                return r.read(VULN_MAX + 1)
    for n, w in warn.items():
        stufen, scores, fixes, ohne = [], [], [], 0
        for vid in w.get("alle") or w["ids"]:
            try:
                raw = get(vid)
                if len(raw) > VULN_MAX:
                    raise ValueError("answer too long")
                vuln = json.loads(raw)
                if not isinstance(vuln, dict):
                    raise ValueError("no record")
            except Exception:   # noqa: BLE001  (one record missing: that hole counts as unknown, without fix)
                stufen.append("unbekannt")
                ohne += 1
                continue
            st, sc, fix = einzeln(vuln, n.split(" ")[0], w["v"])
            stufen.append(st)
            if sc is not None:
                scores.append(sc)
            if fix:
                fixes.append((vkey(fix), fix))
            else:
                ohne += 1
        bekannt = [s for s in stufen if s != "unbekannt"]
        w["stufe"] = min(bekannt, key=STUFEN.index) if bekannt else "unbekannt"
        w["score"] = max(scores) if scores else None
        w["behoben"] = max(fixes)[1] if fixes else None
        w["ohne_fix"] = ohne
    return warn


def main(argv, post=None, heute=None, get=None):
    pak = gepinnt()
    if not pak:
        print("pakete: no pinned package found", flush=True)
        return 2
    pak.update(motoren())
    try:
        warn = frage(pak, post)
    except Exception as e:   # noqa: BLE001  (no network, another answer: no verdict)
        print(f"pakete: osv fehler {type(e).__name__} | {len(pak)} pakete", flush=True)
        return 2
    genauer(warn, get)
    bilder = abbilder()
    old = alt(bilder, heute or datetime.date.today())
    print(f"pakete: osv ok {len(warn)} warnungen {len(pak)} pakete | {len(old)} von {len(bilder)} abbildern alt",
          flush=True)
    if not warn and not old:
        return 0
    lines = []
    if warn:
        lines += ["Gepinnte Python-Pakete mit bekannter Lücke (OSV):", ""]
        lines += [f"- `{n.split(' ')[0]}` {w['v']}: {w['stufe']}"
                  + (f" ({w['score']})" if w.get("score") is not None else "")
                  + (f", behoben in {w['behoben']}" if w.get("behoben") else ", noch kein Fix")
                  + (f" ({w['ohne_fix']} ohne Fix)" if w.get("behoben") and w.get("ohne_fix") else "")
                  + f": {', '.join(w['ids'])}" for n, w in sorted(warn.items())]
    if old:
        lines += ([""] if lines else []) + [f"Docker-Abbilder der Modelle, älter als {DOCKER_TAGE} Tage "
                                            "(neuen Digest suchen, `seit` in app/modelle.py):", ""]
        lines += [f"- `{n}`: {d} Tage" for n, d in old]
    print("\n".join(lines), flush=True)
    daten = os.environ.get("PAKETE_JSON")
    if daten:
        with open(daten, "w", encoding="utf-8") as f:
            json.dump({"pakete": [{"n": n.split(" ")[0], "v": w["v"], "ids": w["ids"], "stufe": w["stufe"],
                                   "score": w["score"], "behoben": w["behoben"], "ohne_fix": w["ohne_fix"]}
                                  for n, w in sorted(warn.items())]}, f, ensure_ascii=False, indent=1)
    note = os.environ.get("PAKETE_NOTE")
    if note:
        with open(note, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
