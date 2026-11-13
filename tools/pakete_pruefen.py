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
import importlib.util
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# app/osv.py is the one place for what goes to OSV and how its answer is read (the Spark uses the same file)
_spec = importlib.util.spec_from_file_location("osv", os.path.join(ROOT, "app", "osv.py"))
osv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(osv)
OSV_URL, OSV_MAX, OSV_ID, PIN, MAX_IDS = osv.OSV_URL, osv.OSV_MAX, osv.OSV_ID, osv.PIN, osv.MAX_IDS
VULN_URL, VULN_MAX, STUFEN = osv.VULN_URL, osv.VULN_MAX, osv.STUFEN
vkey, cvss3, stufe_von, einzeln = osv.vkey, osv.cvss3, osv.stufe_von, osv.einzeln
# modelle.py DOCKER: "image": "<name>@sha256:<64 hex>", and on the next line "seit": "YYYY-MM-DD"
DOCKER = re.compile(r'"image":\s*"([a-z0-9][a-z0-9._/-]{0,127})@sha256:[0-9a-f]{64}",\s*\n\s*"seit":\s*"(\d{4}-\d{2}-\d{2})"')
DOCKER_TAGE = osv.DOCKER_TAGE


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
        return osv.motoren(f.read())

def abbilder(root=ROOT):
    """[(image, day pinned)] of the model engines' Docker images (modelle.DOCKER)."""
    with open(os.path.join(root, "app", "modelle.py"), encoding="utf-8") as f:
        return [(name, datetime.date.fromisoformat(day)) for name, day in DOCKER.findall(f.read())]


def alt(bilder, heute):
    """[(image, days)] pinned longer ago than DOCKER_TAGE days."""
    return [(n, (heute - d).days) for n, d in bilder if (heute - d).days > DOCKER_TAGE]


def apps(root=ROOT):
    """({"name teil": version}, {"name teil": ecosystem}) of what the apps and companions bring along (osv.apps); the
    space keeps them out of Weg 1 (luecke_schliessen.ziele raises only the panel's own lock)."""
    pak, oeko = {}, {}
    for teil, n, v, e in osv.apps(root):
        pak[f"{n} {teil}"], oeko[f"{n} {teil}"] = v, e
    return pak, oeko


def frage(pak, post=None, oeko="PyPI"):
    """{name: {"v", "ids", "alle"}} for the packages OSV knows a hole in; raises when there is no answer."""
    body = json.dumps(osv.anfrage(pak, oeko)).encode()
    if post is None:
        def post(data):
            req = urllib.request.Request(OSV_URL, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:      # noqa: S310  (fixed https address)
                return r.read(OSV_MAX + 1)
    return osv.antwort(pak, post(body))


def genauer(warn, get=None, oeko=None):
    """Weight, fix and holes without a fix for every package in warn (app/osv.zusammen); a record that does not
    come counts as unknown, without a fix."""
    if get is None:
        def get(vid):
            with urllib.request.urlopen(VULN_URL + vid, timeout=30) as r:   # noqa: S310  (fixed https address)
                return r.read(VULN_MAX + 1)
    for n, w in warn.items():
        records = []
        for vid in w.get("alle") or w["ids"]:
            try:
                records.append(osv.eintrag(get(vid)))
            except Exception:   # noqa: BLE001  (one record missing: that hole counts as unknown, without fix)
                records.append(None)
        w.update({k: v for k, v in osv.zusammen(dict(w, name=n.split(" ")[0]), records,
                                                (oeko or {}).get(n, "PyPI")).items()
                  if k in ("stufe", "score", "behoben", "ohne_fix")})
    return warn


def main(argv, post=None, heute=None, get=None):
    pak = gepinnt()
    if not pak:
        print("pakete: no pinned package found", flush=True)
        return 2
    pak.update(motoren())
    app_pak, oeko = apps()
    pak.update(app_pak)
    try:
        warn = frage(pak, post, oeko)
    except Exception as e:   # noqa: BLE001  (no network, another answer: no verdict)
        print(f"pakete: osv fehler {type(e).__name__} | {len(pak)} pakete", flush=True)
        return 2
    genauer(warn, get, oeko)
    bilder = abbilder()
    old = alt(bilder, heute or datetime.date.today())
    print(f"pakete: osv ok {len(warn)} warnungen {len(pak)} pakete | {len(old)} von {len(bilder)} abbildern alt",
          flush=True)
    if not warn and not old:
        return 0
    lines = []
    if warn:
        lines += ["Gepinnte Pakete mit bekannter Lücke (OSV; Python, dazu Apps und Begleiter mit ihrem Teil):", ""]
        lines += [f"- `{n.split(' ')[0]}`" + (f" ({n.split(' ')[1]})" if n in oeko else "") + f" {w['v']}: {w['stufe']}"
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
