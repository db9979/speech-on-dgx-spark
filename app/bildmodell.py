"""Bilder malen (plan plaene/bildgenerierung.md, Dominik 2026-10-14 „1c 2a 3a 4a 5a 6a 7a 8b“): the one list of
the image models, where they lie and how they are fetched and checked. install.sh downloads with it
(`python3 bildmodell.py download VARIANT FOLDER`), bild_server.py starts the engine with its paths, the panel
shows names, sizes and licences from it, and the model catalog (modelle.py) takes them for its picture entries.

FLUX.2 [klein] by Black Forest Labs as GGUF for stable-diffusion.cpp (sd-server), the text encoder Qwen3 (4B for
the 4B model, 8B for the 9B model) and the FLUX.2 VAE. Every file is pinned by its SHA-256 (the Git LFS id of the
file on Hugging Face); a file that does not match is deleted and the install stops for the image part.
The image check (bild_server.check) is a small ViT classifier (int8 ONNX, CPU) for nudity.

Licences: klein 4B Apache 2.0 (also commercial); klein 9B FLUX Non-Commercial License (private use only);
Qwen3 Apache 2.0; the VAE Apache 2.0; the classifier Apache 2.0.
"""
import hashlib
import os
import sys

FOLDER = os.environ.get("SPEECH_SPARK_BILD_DIR", "/var/lib/speech-spark/models/bild")
ENGINE = os.environ.get("SPEECH_SPARK_SD_SERVER", "/opt/speech-spark/sdcpp/bin/sd-server")
# stable-diffusion.cpp, built by install.sh from exactly this commit (tag master-964-1d0a58a, 2026-10-13)
SDCPP_COMMIT = "1d0a58a35050d285b1d6fb1bc68a92924d35825e"


class File:
    def __init__(self, repo, revision, path, sha256, size):
        self.repo, self.revision, self.path, self.sha256, self.size = repo, revision, path, sha256, size

    @property
    def name(self):
        return os.path.basename(self.path)


_K4 = "leejet/FLUX.2-klein-4B-GGUF", "3b1f5a9dc3abb32238b053aeb3d823c30afdacbd"
_K9 = "leejet/FLUX.2-klein-9B-GGUF", "cc588497a95ffc2937ebbd6b9b3916a11ada6e5b"
_Q4 = "unsloth/Qwen3-4B-GGUF", "22c9fc8a8c7700b76a1789366280a6a5a1ad1120"
_Q8 = "unsloth/Qwen3-8B-GGUF", "a6adef130ffb23ddaf1a62fec9dced968c9bc482"
VAE = File("Comfy-Org/flux2-klein-4B", "main", "split_files/vae/flux2-vae.safetensors",
           "868fe7b343cc8f3a19dbcfcafbc3d5f888802be3f89bd81b65b3621a066ce8f3", 336211292)
CHECKER = File("AdamCodd/vit-base-nsfw-detector", "main", "onnx/model_quantized.onnx",
               "432763a6899ebc418c55f784b98f90565e5fc694c778d2ffcb0294b12f6a7404", 88500985)
CHECK_SIDE = 384           # the classifier's input (ViTImageProcessor: 384 x 384, mean 0.5, std 0.5)

# variant -> name, licence, diffusion model, text encoder, unified memory while painting (GiB, an estimate until
# the measurement on tars: weights + about 2 GiB working memory), seconds the engine may take to load
VARIANTS = {
    "4b-q8": {"name": "FLUX.2 [klein] 4B · Q8", "license": "Apache 2.0", "commercial": True, "need_gib": 11,
              "model": File(*_K4, "flux-2-klein-4b-Q8_0.gguf",
                            "0bba6951258ec8f92d51114a8fa13e66828297bfff58a738f52729b3ef66fa28", 4300629440),
              "llm": File(*_Q4, "Qwen3-4B-Q8_0.gguf",
                          "eed555233267a33c7e8ee31682762cc7751b3f6d224039086e0e846f05fffa5d", 4280405792)},
    "4b-q4": {"name": "FLUX.2 [klein] 4B · Q4", "license": "Apache 2.0", "commercial": True, "need_gib": 7,
              "model": File(*_K4, "flux-2-klein-4b-Q4_0.gguf",
                            "d1023499ef3f2f82ff7c50e6778495195c1b6cc34835741778868428111f9ff4", 2460378560),
              "llm": File(*_Q4, "Qwen3-4B-Q4_K_M.gguf",
                          "f6f851777709861056efcdad3af01da38b31223a3ba26e61a4f8bf3a2195813a", 2497281312)},
    "9b-q8": {"name": "FLUX.2 [klein] 9B · Q8", "license": "FLUX Non-Commercial", "commercial": False, "need_gib": 22,
              "model": File(*_K9, "flux-2-klein-9b-Q8_0.gguf",
                            "67ca777c7aa2d6a0d63d4a7564f823c63af88e9688643df727e1867789062982", 9978284192),
              "llm": File(*_Q8, "Qwen3-8B-Q8_0.gguf",
                          "0cfbf745760f07a76ddeb358dd025a27f2e11d1ca9c9a4169a373d52990fe86e", 8709519168)},
    "9b-q4": {"name": "FLUX.2 [klein] 9B · Q4", "license": "FLUX Non-Commercial", "commercial": False, "need_gib": 13,
              "model": File(*_K9, "flux-2-klein-9b-Q4_0.gguf",
                            "a7e77afa96871d16679ff7b949bd25f20c8179f219c4b662cac91e81ed99b944", 5616208032),
              "llm": File(*_Q8, "Qwen3-8B-Q4_K_M.gguf",
                          "120307ba529eb2439d6c430d94104dabd578497bc7bfe7e322b5d9933b449bd4", 5027784512)},
}
DEFAULT = "4b-q8"
STEPS = 4                  # the distilled klein models: 4 steps, guidance 1.0 (model card)
GUIDANCE = 1.0


def variant(v):
    """A known variant name (anything else from a hand-edited config falls back to the default)."""
    return v if v in VARIANTS else DEFAULT


def files(v):
    """Every file the variant needs, the image check included."""
    m = VARIANTS[variant(v)]
    return [m["model"], m["llm"], VAE, CHECKER]


def path(f, folder=None):
    return os.path.join(folder or FOLDER, f.name)


def disk_gb(v):
    return round(sum(f.size for f in files(v)) / 1e9, 1)


def installed(v, folder=None):
    """All files there with their size (the hash is checked once when they are fetched) and the engine built."""
    return all(file_size(path(f, folder)) == f.size for f in files(v)) and os.access(ENGINE, os.X_OK)


def missing(v, folder=None):
    """What is not there yet: names of files, and "engine" when sd-server is not built."""
    out = [f.name for f in files(v) if file_size(path(f, folder)) != f.size]
    if not os.access(ENGINE, os.X_OK):
        out.append("engine")
    return out


def file_size(p):
    """The size of a plain file (a link counts as missing: -1), -1 when it is not there."""
    try:
        return os.stat(p).st_size if not os.path.islink(p) else -1
    except OSError:
        return -1


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def download(v, folder):
    """Fetches what the variant is missing into folder (as the service user, called by install.sh)."""
    return fetch(files(v), folder)


def fetch(wanted, folder):
    """Fetches the files that are missing into folder and checks each file's size and SHA-256; a file that does not
    match is deleted. Returns True when everything is there. musikmodell.py fetches its files with it too."""
    from huggingface_hub import hf_hub_download
    os.makedirs(folder, exist_ok=True)
    ok = True
    for f in wanted:
        dest = path(f, folder)
        if file_size(dest) == f.size:
            continue
        print(f"   {f.name} ({f.size / 1e9:.1f} GB) from {f.repo}", flush=True)
        try:
            got = hf_hub_download(f.repo, f.path, revision=f.revision, local_dir=os.path.join(folder, ".dl"))
        except Exception as e:
            print(f"   {f.name}: download failed ({type(e).__name__})", flush=True)
            ok = False
            continue
        if os.path.islink(got) or file_size(got) != f.size or sha256(got) != f.sha256:
            print(f"   {f.name}: size or SHA-256 does not match, deleted", flush=True)
            os.unlink(got)
            ok = False
            continue
        os.replace(got, dest)
    return ok

if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "download" and sys.argv[2] in VARIANTS:
        sys.exit(0 if download(sys.argv[2], sys.argv[3]) else 1)
    print("usage: bildmodell.py download VARIANT FOLDER", file=sys.stderr)
    sys.exit(2)
