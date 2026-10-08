#!/usr/bin/env python3
"""Packs the files of one XiaoZhi build for the Spark (run in the firmware workflow).

    package.py variant <xiaozhi dir> <variant name> <label> <out dir>
        copies the flash files named in build/flasher_args.json as <variant>__<file> and writes
        <variant>.json with address, file, size and SHA-256 of each part
    package.py manifest <dir with the variant folders> <version> <commit> <wake word label> <out dir>
        collects everything into one flat folder with manifest.json (what the Spark downloads)
"""
import datetime
import hashlib
import json
import os
import shutil
import sys


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def variant(src, name, label, out):
    os.makedirs(out, exist_ok=True)
    build = os.path.join(src, "build")
    with open(os.path.join(build, "flasher_args.json")) as f:
        fa = json.load(f)
    parts = []
    for addr, rel in sorted(fa["flash_files"].items(), key=lambda x: int(x[0], 16)):
        fn = f"{name}__{os.path.basename(rel)}"
        shutil.copy(os.path.join(build, rel), os.path.join(out, fn))
        parts.append({"address": int(addr, 16), "file": fn, "size": os.path.getsize(os.path.join(out, fn)),
                      "sha256": sha(os.path.join(out, fn))})
    app = os.path.basename(fa["app"]["file"])
    app_part = next(p for p in parts if p["file"] == f"{name}__{app}")
    with open(os.path.join(build, "config", "sdkconfig.json")) as f:
        sdk = json.load(f)
    flash = sdk.get("ESPTOOLPY_FLASHSIZE", "16MB")
    with open(os.path.join(out, name + ".json"), "w") as f:
        json.dump({"name": name, "label": label, "flash": flash, "parts": parts,
                   "app": {"file": app_part["file"], "sha256": app_part["sha256"], "size": app_part["size"]}}, f, indent=1)


def manifest(src, version, commit, wake, out):
    os.makedirs(out, exist_ok=True)
    variants = {}
    for root, _, files in os.walk(src):
        for fn in files:
            path = os.path.join(root, fn)
            if fn.endswith(".json"):
                with open(path) as f:
                    v = json.load(f)
                variants[v.pop("name")] = v
            else:
                shutil.copy(path, os.path.join(out, fn))
    if not variants:
        sys.exit("no variants built")
    for name, v in variants.items():
        for p in v["parts"]:
            if sha(os.path.join(out, p["file"])) != p["sha256"]:
                sys.exit(f"{p['file']}: checksum changed")
    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump({"version": version, "xiaozhi_commit": commit, "wake_word": wake,
                   "built": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "variants": variants}, f, indent=1)


if __name__ == "__main__":
    if sys.argv[1] == "variant":
        variant(*sys.argv[2:6])
    elif sys.argv[1] == "manifest":
        manifest(*sys.argv[2:7])
    else:
        sys.exit(__doc__)
