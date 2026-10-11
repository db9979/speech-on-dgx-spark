"""Keeps the repo's releases tidy (V01.0.371): per release series only the newest one stays, older ones
go together with their tag. A series is the tag without its version number (fw-2.5.1.6 → fw-,
android-v1.1.0 → android-v); a tag without a number (begleiter-windows, begleiter-mac) is a series of
its own and is replaced in place by its workflow. RETIRED lists series no workflow builds any more.

Nothing on the Spark needs an older release: firmware and Android app take the newest fw-…/android-v…
and keep the version before locally (esp32.py, android.py), the Begleiter reads its fixed tag
(begleiter.py), TestFlight uses no release. Drafts and pre-releases are never touched.

Run by .github/workflows/releases-aufraeumen.yml after a successful release run, or by hand.
Usage: python3 releases_aufraeumen.py [--dry-run]   (needs GH_TOKEN and GITHUB_REPOSITORY)"""
import json
import os
import re
import subprocess
import sys

RETIRED = {"schreibhilfe-windows"}  # replaced by the Spark-Begleiter (begleiter-windows), V01.0.342
TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\-]{0,99}")
VERSIONED = re.compile(r"(.*?)\d+(?:\.\d+)*")


def series(tag):
    m = VERSIONED.fullmatch(tag)
    return m.group(1) if m and m.group(1) else tag


def plan(releases):
    """The tags to delete: in every series all but the newest published release, plus retired series."""
    groups = {}
    for r in releases:
        tag = str(r.get("tag_name") or "")
        if r.get("draft") or r.get("prerelease") or not TAG.fullmatch(tag) or not r.get("published_at"):
            continue
        groups.setdefault(series(tag), []).append(r)
    out = []
    for name, rs in groups.items():
        rs.sort(key=lambda r: r["published_at"], reverse=True)
        drop = rs if name in RETIRED else rs[1:]
        out += [r["tag_name"] for r in drop]
    return sorted(out)


def main():
    dry = "--dry-run" in sys.argv[1:]
    repo = os.environ["GITHUB_REPOSITORY"]
    if not re.fullmatch(r"[\w.\-]+/[\w.\-]+", repo):
        sys.exit("GITHUB_REPOSITORY is not owner/name")
    raw = subprocess.run(["gh", "api", "--paginate", f"repos/{repo}/releases?per_page=100", "--jq", ".[] | @json"],
                         check=True, capture_output=True, text=True).stdout
    releases = [json.loads(line) for line in raw.splitlines() if line.strip()]
    tags = plan(releases)
    keep = sorted({r["tag_name"] for r in releases} - set(tags))
    print("stays:", ", ".join(keep) or "-")
    print("goes:", ", ".join(tags) or "-")
    for tag in tags:
        if not dry:
            subprocess.run(["gh", "release", "delete", tag, "--repo", repo, "--cleanup-tag", "--yes"], check=True)
            print("deleted", tag, flush=True)


if __name__ == "__main__":
    main()
