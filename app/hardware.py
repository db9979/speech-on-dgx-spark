"""Hardware-Profil (Dominik 2026-11-16 „1-6“, plan /mnt/project-files/modellkatalog/vorschlaege.html, stage A): which
kind of computer the models run on, so the catalog can name GiB instead of a share of the GB10's memory and the same
catalog fits a DGX Spark and later a DGX Station.

- gb10: DGX Spark. CPU and GPU share one memory (about 120 GiB); the engines' share is a share of that.
- gb300: DGX Station. The GPU has its own memory (HBM, about 280 GiB) beside the CPU's (LPDDR5X, about 500 GiB);
  the engines' share is a share of the GPU's memory, the small CPU models live in the CPU's.
- andere: any other GPU, counted like the Station when nvidia-smi names its own memory, else like the Spark.
- ohne_gpu: no nvidia-smi (the panel computer, the tests): the Spark's numbers with BEZUG_GIB, so nothing depends on
  the memory of the computer the tests run on.

Only one fixed command reads it (nvidia-smi with fixed query fields, no argument from anywhere else); the GPU's name
is kept only as one of the fixed words of PROFILE. Read once per process (the hardware does not change while it runs).
"""
import functools
import os
import re
import shutil

from common import run

BEZUG_GIB = 120.0       # the reference pool: a DGX Spark, the computer every catalog number was first measured on
SYSTEM_GIB = {"gemeinsam": 6, "getrennt": 2}   # DGX OS, the panel and small services / only the CUDA contexts on the GPU
PROFILE = {
    "gb10": {"de": "DGX Spark (GB10)", "en": "DGX Spark (GB10)"},
    "gb300": {"de": "DGX Station (GB300)", "en": "DGX Station (GB300)"},
    "andere": {"de": "anderer NVIDIA-Rechner", "en": "other NVIDIA computer"},
    "ohne_gpu": {"de": "ohne GPU", "en": "without GPU"},
}
KENNUNG = (("GB300", "gb300"), ("GB10", "gb10"))     # the GPU's name contains … → profile (first match wins)
FELDER = ("id", "gemeinsam", "pool_gib", "ram_gib", "system_gib")
# the recommendation in the catalog (modelle.json "empfohlen", Dominik 2026-11-16 „1-3“): which kind of computer a
# profile counts as; another GPU with at least STATION_AB_GIB of its own memory like the Station, else like the Spark
KLASSEN = ("gb10", "gb300")
STATION_AB_GIB = 200
# the profiles whose GPU runs NVFP4 (Blackwell): the search puts NVFP4 first there, elsewhere FP8
FP4 = ("gb10", "gb300")


def _ram_gib():
    return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1)


def aus_smi(code, out, ram_gib):
    """The profile from nvidia-smi's answer to `--query-gpu=name,memory.total --format=csv,noheader,nounits`.
    pool_gib: the memory the engines' share (--gpu-memory-utilization) refers to."""
    zeile = out.splitlines()[0] if code == 0 and out else ""
    teile = [x.strip() for x in zeile.split(",")]
    if len(teile) != 2:
        return {"id": "ohne_gpu", "gemeinsam": True, "pool_gib": BEZUG_GIB, "ram_gib": BEZUG_GIB,
                "system_gib": SYSTEM_GIB["gemeinsam"]}
    name, mib = teile
    pid = next((p for k, p in KENNUNG if k in name.upper()), "andere")
    gpu = int(mib) / 1024 if re.fullmatch(r"\d{3,8}", mib) else None
    if pid == "gb10" or gpu is None:          # the GB10 says [N/A]: its GPU uses the one shared memory
        return {"id": pid, "gemeinsam": True, "pool_gib": ram_gib, "ram_gib": ram_gib,
                "system_gib": SYSTEM_GIB["gemeinsam"]}
    return {"id": pid, "gemeinsam": False, "pool_gib": round(gpu, 1), "ram_gib": ram_gib,
            "system_gib": SYSTEM_GIB["getrennt"]}


@functools.lru_cache(maxsize=1)
def profil():
    """This computer's profile (FELDER), read once."""
    if not shutil.which("nvidia-smi"):
        return aus_smi(1, "", BEZUG_GIB)
    code, out = run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], timeout=15)
    return aus_smi(code, out, _ram_gib())


def gueltig(p):
    """A profile as the Wärter sends it to the panel computer: only FELDER, a known id, numbers in range; else None."""
    if not isinstance(p, dict) or set(p) != set(FELDER) or p.get("id") not in PROFILE:
        return None
    zahlen = [p[k] for k in ("pool_gib", "ram_gib", "system_gib")]
    if not isinstance(p["gemeinsam"], bool) or any(isinstance(x, bool) or not isinstance(x, (int, float))
                                                   or not 0 < x <= 4096 for x in zahlen):
        return None
    return p


def klasse(p):
    """gb10 or gb300: the kind of computer whose recommendation fits this profile."""
    if p.get("id") in KLASSEN:
        return p["id"]
    return "gb300" if p.get("id") == "andere" and not p.get("gemeinsam") and p.get("pool_gib", 0) >= STATION_AB_GIB else "gb10"


def text(p, lang="de"):
    """One line for the pages: the computer and its memory (fixed words and numbers)."""
    name = PROFILE.get(p.get("id"), PROFILE["andere"])["en" if lang == "en" else "de"]
    zahl = (lambda x: f"{x:g}") if lang == "en" else (lambda x: f"{x:g}".replace(".", ","))
    if p.get("gemeinsam"):
        return f"{name} · {zahl(p['pool_gib'])} GiB " + ("shared" if lang == "en" else "gemeinsam")
    return (f"{name} · {zahl(p['pool_gib'])} GiB GPU + {zahl(p['ram_gib'])} GiB "
            + ("memory" if lang == "en" else "Arbeitsspeicher"))
