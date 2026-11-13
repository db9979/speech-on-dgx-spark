"""OSV, the one place (Schwachstellen, Dominik 2026-11-13): what goes out to the OSV database and how its answer is
read, for the Spark (panel/schwachstellen.py, panel/systemupdates.py) and for GitHub (tools/pakete_pruefen.py,
tools/luecke_schliessen.py, tools/vorpush.py). Only package names and versions go out (one batch question), then
only ids (one question per id for weight and fix); only ids, numbers and versions in a fixed character set come
back. OSV's texts (summary, details) are never read. No network here: the callers send (urllib on GitHub, the
netguard client on the Spark), so this file has no dependency and runs with GitHub's plain python3.
"""
import json
import os
import re

OSV_URL = "https://api.osv.dev/v1/querybatch"
OSV_MAX = 2 * 1048576
BATCH = 1000                                         # questions per batch, OSV's own limit
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
    """The batch question for {name: version} (a name with a space is asked as its first word); oekosystem is one
    for all or {name: ecosystem} (PyPI where it names none)."""
    def oeko(n):
        return oekosystem.get(n, "PyPI") if isinstance(oekosystem, dict) else oekosystem
    return {"queries": [{"package": {"name": n.split(" ")[0], "ecosystem": oeko(n)}, "version": v}
                        for n, v in pak.items()]}


# the apps' and companions' parts (Paket 3): where they are written down in the repository, the one list
APP_TEILE = {"ios": "iPhone-App", "android": "Android-App", "pebble": "Pebble-App", "begleiter": "Begleiter", "panel-js": "Panel (JavaScript)"}
GRADLE_PLUGIN = {"com.android.application": "com.android.tools.build:gradle",
                 "org.jetbrains.kotlin.android": "org.jetbrains.kotlin:kotlin-gradle-plugin"}
GRADLE_ID = re.compile(r'id\("([a-z0-9.]+)"\) version "([0-9][0-9A-Za-z.\-]{0,39})"')
NUGET = re.compile(r'<PackageReference Include="([A-Za-z0-9.\-]{1,80})" Version="([0-9][0-9A-Za-z.\-]{0,39})"')
VENDOR_JS = (("app/panel/fernbild.py", re.compile(r'^GUAC_VERSION = "([0-9][0-9.]{0,19})"', re.M), "guacamole-common-js"),)


def _lies(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def apps(root):
    """[(teil, name, version, ecosystem)] of what the apps and companions bring along, read from the repository at
    root (nothing in a copy with only app/): the iPhone app's Swift packages (Package.resolved), the Android app's
    build plugins, the companions' NuGet packages, the npm packages of the Pebble app and the JavaScript the panel
    ships vendored (guacamole-common-js)."""
    out = []
    try:
        res = json.loads(_lies(root, "ios/Spark.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved") or "{}")
    except ValueError:
        res = {}
    for pin in res.get("pins") or []:
        loc, ver = str((pin or {}).get("location", "")), str(((pin or {}).get("state") or {}).get("version") or "")
        m = re.fullmatch(r"https://(github\.com/[A-Za-z0-9_.\-]{1,60}/[A-Za-z0-9_.\-]{1,60}?)(?:\.git)?", loc)
        if m and FIX.fullmatch(ver):
            out.append(("ios", m.group(1), ver, "SwiftURL"))
    for n, v in GRADLE_ID.findall(_lies(root, "android/build.gradle.kts")):
        if n in GRADLE_PLUGIN:
            out.append(("android", GRADLE_PLUGIN[n], v, "Maven"))
    for rel in ("tools/begleiter/windows/SparkBegleiter.csproj", "tools/begleiter/outlook-classic/SparkOutlook.csproj",
                "tools/sparkhilfe/windows/SparkHilfe.csproj"):
        out += [("begleiter", n, v, "NuGet") for n, v in NUGET.findall(_lies(root, rel))]
    for rel in ("pebble/package.json", "pebble/zifferblatt/package.json"):
        try:
            deps = json.loads(_lies(root, rel) or "{}").get("dependencies") or {}
        except ValueError:
            deps = {}
        for n, v in deps.items() if isinstance(deps, dict) else ():
            v = str(v).lstrip("^~=")
            if re.fullmatch(r"[a-z0-9@][a-z0-9._/\-]{0,80}", str(n)) and FIX.fullmatch(v):
                out.append(("pebble", n, v, "npm"))
    for rel, rx, name in VENDOR_JS:
        m = rx.search(_lies(root, rel))
        if m:
            out.append(("panel-js", name, m.group(1), "npm"))
    seen, uniq = set(), []
    for x in out:
        if (x[1], x[2], x[3]) not in seen:
            seen.add((x[1], x[2], x[3]))
            uniq.append(x)
    return uniq


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
