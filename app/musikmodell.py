"""Musik machen (plan plaene/musik.md, Dominik 2026-10-16 „1a 2a 3a 4a 5a“): the one list of the music models,
where they lie and how they are fetched and checked. install.sh downloads with it
(`python3 musikmodell.py download VARIANT FOLDER`), musik_server.py starts the engine with its paths, the panel
shows names, sizes and licences from it, and the model catalog (modelle.py) takes them for its music entries.

ACE-Step 1.5 as GGUF for acestep.cpp (ace-server, C++/GGML, no torch): the DiT that makes the sound (2B or XL 4B,
"turbo" with 8 steps), a small language model that plans the song (0.6B or 1.7B, Qwen3-based), the text encoder
(Qwen3-Embedding 0.6B) and the VAE. Every file is pinned by its SHA-256 (the Git LFS id of the file on Hugging Face,
revision below); a file that does not match is deleted and the install stops for the music part. The file class,
the checks and the download are bildmodell's (one place); install.sh hands both files to the service user.

Licences: ACE-Step 1.5 code and weights MIT; Qwen3-Embedding Apache 2.0. The ACE-Step README asks to check the
training data question yourself before publishing or selling music made with it: the panel says "for private use".
"""
import os
import sys

from bildmodell import File, fetch, file_size, path

FOLDER = os.environ.get("SPEECH_SPARK_MUSIK_DIR", "/var/lib/speech-spark/models/musik")
ENGINE = os.environ.get("SPEECH_SPARK_ACE_SERVER", "/opt/speech-spark/acestep/bin/ace-server")
# acestep.cpp, built by install.sh from exactly this commit (2026-10-12 "cli: select the GGML device with --device")
ACECPP_COMMIT = "6013134c136d9fb4e970cf690e76925be9553da0"
ACECPP_REPO = "https://github.com/ServeurpersoCom/acestep.cpp"


_GG = "Serveurperso/ACE-Step-1.5-GGUF", "9b3707625776cc4cf775e9b12ab82f9fe48335ff"
VAE = File(*_GG, "vae-BF16.gguf", "0599862ac5d15cd308e1d2e368373aea6c02e25ebd1737ad4a4562a0901b0ef8", 337420928)
TEXT = File(*_GG, "Qwen3-Embedding-0.6B-Q8_0.gguf",
            "972f23255e46adfe744a0eb9a0039f3c63988f65753b0968d776e8b27168c321", 784144960)
LM06 = File(*_GG, "acestep-5Hz-lm-0.6B-Q8_0.gguf",
            "bdaf9e292d4470f31c19cafeaca1b74936a114667e3a85e5d33b65247e9908ec", 709846656)
LM17 = File(*_GG, "acestep-5Hz-lm-1.7B-Q8_0.gguf",
            "726f99a82f050b32ebc5c5e36acaa9d7acd06bfe5e579a62b00e0d0d6d0b7ec6", 1975837568)
DIT2B = File(*_GG, "acestep-v15-turbo-Q8_0.gguf",
             "288f708a61cfc241013a98a62f98ba331f83fe34d0d3559acdd9b0f6a2f7cd6b", 2549528000)
DITXL = File(*_GG, "acestep-v15-xl-turbo-Q8_0.gguf",
             "4f1044fb646374fb5730e10f64325766883eb2fc02a643c1b403f2d61f39dc19", 5305828736)

# variant -> name, the sound model (DiT), the song planner (LM), unified memory while making music (GiB, an estimate
# until the measurement on tars, stage M0: the largest module plus working memory; ace-server keeps one at a time)
VARIANTS = {
    "2b": {"name": "ACE-Step 1.5 · 2B turbo + 1.7B", "need_gib": 10, "dit": DIT2B, "lm": LM17},
    "2b-klein": {"name": "ACE-Step 1.5 · 2B turbo + 0.6B", "need_gib": 7, "dit": DIT2B, "lm": LM06},
    "xl": {"name": "ACE-Step 1.5 · XL turbo + 1.7B", "need_gib": 16, "dit": DITXL, "lm": LM17},
}
DEFAULT = "2b"
LICENSE = "MIT"
STEPS = 8                  # the turbo models: 8 steps (model card)
MP3_KBPS = 192


def variant(v):
    """A known variant name (anything else from a hand-edited config falls back to the default)."""
    return v if v in VARIANTS else DEFAULT


def files(v):
    m = VARIANTS[variant(v)]
    return [m["dit"], m["lm"], TEXT, VAE]


def disk_gb(v):
    return round(sum(f.size for f in files(v)) / 1e9, 1)


def installed(v, folder=None):
    """All files there with their size (the hash is checked once when they are fetched) and the engine built."""
    return not missing(v, folder)


def missing(v, folder=None):
    """What is not there yet: names of files, and "engine" when ace-server is not built. bildmodell.path falls back to
    the picture folder, so the music folder is always passed on (V01.0.672: the files were looked for there)."""
    out = [f.name for f in files(v) if file_size(path(f, folder or FOLDER)) != f.size]
    if not os.access(ENGINE, os.X_OK):
        out.append("engine")
    return out


def download(v, folder):
    """Fetches what the variant is missing into folder (as the service user, called by install.sh), each file
    checked by size and SHA-256 (bildmodell.fetch)."""
    return fetch(files(v), folder)

if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "download" and sys.argv[2] in VARIANTS:
        sys.exit(0 if download(sys.argv[2], sys.argv[3]) else 1)
    print("usage: musikmodell.py download VARIANT FOLDER", file=sys.stderr)
    sys.exit(2)
