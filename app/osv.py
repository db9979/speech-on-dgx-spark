"""OSV, the one place (Schwachstellen, Dominik 2026-11-13): what goes out to the OSV database and how its answer is
read, for the Spark (panel/schwachstellen.py, panel/systemupdates.py) and for GitHub (tools/pakete_pruefen.py,
tools/luecke_schliessen.py, tools/vorpush.py). Only package names and versions go out (one batch question), then
only ids (one question per id for weight and fix); only ids, numbers and versions in a fixed character set come
back. OSV's texts (summary, details) are never read. No network here: the callers send (urllib on GitHub, the
netguard client on the Spark), so this file has no dependency and runs with GitHub's plain python3.
"""
import json
import re

OSV_URL = "https://api.osv.dev/v1/querybatch"
OSV_MAX = 2 * 1048576
VULN_URL = "https://api.osv.dev/v1/vulns/"           # + one id: weight and fixed versions of one hole
VULN_MAX = 1048576
OSV_ID = re.compile(r"[A-Z][A-Za-z0-9\-]{2,40}")
# one pinned line of a lock file: name==version
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._\-]{0,63})==([A-Za-z0-9.+!\-]{1,40})\s")
MAX_IDS = 5                                          # ids shown per package
ALLE_IDS = 30                                        # ids asked for weight and fix per package
# the weight of a hole, worst first; GitHub's own words map onto it
STUFEN = ("kritisch", "hoch", "mittel", "niedrig", "unbekannt")
GHSA_STUFE = {"CRITICAL": "kritisch", "HIGH": "hoch", "MODERATE": "mittel", "MEDIUM": "mittel", "LOW": "niedrig"}
VERSION = re.compile(r"^v?(\d+(?:\.\d+)*)(?:[-_.]?(a|b|c|rc|alpha|beta)[-_.]?(\d*))?(?:[-_.]?post[-_.]?(\d*))?"
                     r"(?:[-_.]?dev[-_.]?(\d*))?(?:\+[A-Za-z0-9.]+)?$", re.I)
# what the Spark pins outside the lock files, read by both sides: the engines' versions in install.sh (one line each,
# as install.sh reads them; the name on PyPI) and the age after which a model's Docker image is named
ENGINE = re.compile(r"^(VLLM|VLLM_OMNI|VLLM_LLM)_VERSION=([0-9][0-9A-Za-z.+!\-]{0,39})$", re.M)
ENGINE_NAME = {"VLLM": "vllm", "VLLM_OMNI": "vllm-omni", "VLLM_LLM": "vllm"}
DOCKER_TAGE = 90
FIX = re.compile(r"[0-9][0-9A-Za-z.+!\-]{0,39}")


def anfrage(pak, oekosystem="PyPI"):
    """The batch question for {name: version} (a name with a space is asked as its first word)."""
    return {"queries": [{"package": {"name": n.split(" ")[0], "ecosystem": oekosystem}, "version": v}
                        for n, v in pak.items()]}


def motoren(text):
    """{name: version} of the engines pinned in install.sh's text. A second vLLM with another version than
    VLLM_VERSION is asked as "vllm <version>" (the name sent to OSV is the first word)."""
    out = {}
    for var, ver in ENGINE.findall(text):
        name = ENGINE_NAME[var]
        out[name if out.get(name, ver) == ver else f"{name} {ver}"] = ver
    return out


def antwort(pak, raw):
    """{name: {"v", "ids", "alle"}} for the packages OSV knows a hole in, from the answer as bytes or as read JSON
    (the Spark's client limits the size itself); raises when the answer does not fit."""
    if isinstance(raw, (bytes, str)):
        if len(raw) > OSV_MAX:
            raise ValueError("answer too long")
        raw = json.loads(raw)
    res = (raw if isinstance(raw, dict) else {}).get("results")
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


def einzeln(vuln, name, ver, oekosystem="PyPI"):
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
        if pkg.get("ecosystem") != oekosystem or norm(pkg.get("name")) != norm(name):
            continue
        for rng in aff.get("ranges") or []:
            for ev in (rng or {}).get("events") or []:
                k = vkey((ev or {}).get("fixed"))
                if k is not None and have is not None and k > have:
                    fixes.append((k, str(ev["fixed"])))
    return stufe, score, (min(fixes)[1] if fixes else None)


def zusammen(w, records, oekosystem="PyPI"):
    """Adds to one package w: "stufe" (worst), "score", "behoben" (the version closing every hole that has a fix) and
    "ohne_fix" (holes OSV names no fix for), from its records (None for a record that did not come)."""
    stufen, scores, fixes, ohne = [], [], [], 0
    name = w.get("name", "")
    for vuln in records:
        if not isinstance(vuln, dict):
            stufen.append("unbekannt")
            ohne += 1
            continue
        st, sc, fix = einzeln(vuln, name, w["v"], oekosystem)
        stufen.append(st)
        if sc is not None:
            scores.append(sc)
        if fix and FIX.fullmatch(fix):
            fixes.append((vkey(fix), fix))
        else:
            ohne += 1
    bekannt = [s for s in stufen if s != "unbekannt"]
    w["stufe"] = min(bekannt, key=STUFEN.index) if bekannt else "unbekannt"
    w["score"] = max(scores) if scores else None
    w["behoben"] = max(fixes)[1] if fixes else None
    w["ohne_fix"] = ohne
    return w


def eintrag(raw):
    """One record from OSV's answer, None when it is no record or too long."""
    try:
        if len(raw) > VULN_MAX:
            return None
        vuln = json.loads(raw)
        return vuln if isinstance(vuln, dict) else None
    except ValueError:
        return None
