"""Modell-Katalog (plan plaene/eigene-modelle.md, Dominik 2026-10-14 „1a 2a 3a 4a 5a 6a“): the models this
installation runs itself, one line each in modelle.json, read only here.

Stage E0 measures before anything switches: `sudo speech-spark modelle messen [llm] [sehen] [flash] [helfer] …` stops
the running language model for a while (with a Wartungspause), starts one catalog model at a time natively with vLLM
on 127.0.0.1:MESS_PORT and measures it with fixed German questions, one tool call and fixed test pictures, then
starts the language model again. The result goes to STATE/modelle-messung.json and into the journal ("modelle:" lines with
fixed words and numbers, never an answer's text). Nothing is switched by a measurement and nothing is deleted.
A main model candidate is also measured with 2 and 4 long questions at once and one question of about 60K tokens, and
the engine's own count of the context room (Dominik 2026-10-17: 2-4 at once with a context of 64K or more).

A variant ("basis": an earlier entry's id) takes that entry and changes only the fields it names, its vllm fields
merged (one source: Qwen3.6 with and without MTP).

Rules for every entry (test_modelle): the engine is one we know, the repository a plain "owner/name", the revision
a full commit or empty (empty only to measure), the memory in GiB (gpu_gib; the share of this computer's pool, see
hardware.py, at most ANTEIL_MAX: above ~0.80 the GB10 freezes),
never trust_remote_code, only the flags vllm_args builds from the fields in VLLM_KEYS. Downloads take only the
file kinds in ERLAUBT (no pickle, no Python code) and pruefen() checks every file against its name in the
Hugging Face cache (SHA-256 for large files, the git blob hash for small ones).

Command line (as the panel's service user, from speech-spark.sh): liste · feld <id> repo|revision · messliste <was …> · vorbereiten <id> ·
pruefen <id> [revision] · vllm-args <id> [--port N] [--revision R] [--ohne-mtp] · messen-lauf <id> [--port N]
[--einheit unit] [--revision R] · ergebnis · venv <id>|llm|sehen|helfer · start-args llm|sehen|helfer (engine.sh) · signatur llm|sehen|helfer
(install.sh) · neustart-pruefen · laden <id> (speech-spark-wechsel) · docker-bild <id> ·
docker-args <id> --revision R --name N --uid U --gid G [--ohne-mtp] (mess_docker) · fest <repo> ·
erlaubt (install.sh dl, engine.sh: the pinned commit of a speech model and the file kinds to fetch).

An entry with a Docker recipe (vllm "docker", DOCKER) runs as a container only while it is measured (Dominik
2026-10-17: Docker only on tars, only for model engines): pinned image, no network, its socket put on 127.0.0.1 by
dockertor.py; switching to it is the next stage.

Stage E2 starts the own language model: speech-spark-llm (engine.sh llm) and, on demand, speech-spark-sehen
(engine.sh sehen) and speech-spark-helfer (engine.sh helfer, the small helper model) run `vllm serve` with
start_args(): config llm.modell / llm.sehen_modell / llm.helfer_modell, a pinned commit only (the catalog's or the
one `modelle messen` checked), on 127.0.0.1 behind the LLM-Tor (llm_tor.py, llm.port).
"""
import base64
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import MODEL_LOG_UNITS, STATE, klon_noetig, load_config, mem_available_gib, read_json, write_json  # noqa: E402
import hardware  # noqa: E402
import hftoken  # noqa: E402

KATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modelle.json")
MESSUNG = os.path.join(STATE, "modelle-messung.json")
ARTEN = {"llm": ("Sprachmodell", "Language model"), "sehen": ("Bildverständnis", "Image understanding"),
         "asr": ("Spracherkennung", "Speech recognition"), "tts": ("Sprachausgabe", "Speech output"),
         "bild": ("Bilder malen", "Painting pictures"), "musik": ("Musik machen", "Making music"),
         "klein": ("Kleine Modelle (CPU)", "Small models (CPU)"), "helfer": ("Hilfsmodell", "Helper model")}
# vllm: an engine this installation starts itself (the strict rules below); the others are run as before by their
# own services and are listed for the budget: the speech models, sd.cpp, acestep.cpp, ONNX on the CPU
ENGINES = ("vllm", "qwen-asr", "qwen-tts", "sdcpp", "acestepcpp", "onnx-cpu")
BETRIEB = ("resident", "bei_bedarf")
MESSEN = ("immer", "auf_wunsch")
ANTEIL_MAX = 0.80
GPU_GIB_MAX = 1024     # gpu_gib of one engine: what vLLM reserves for weights and context, in GiB (any computer)
MESS_PORT = 31016
VLLM_KEYS = ("reasoning_parser", "tool_call_parser", "mtp", "max_seqs", "quantization", "bilder_pro_frage", "kv_cache_dtype",
             "venv", "docker", "entwurf", "entwurf_revision", "batched_tokens")
# a separate draft model for speculative decoding (Gemma 4's „assistant“, Dominik 2026-11-13 „1“): only a repository
# name; fetched and checked like the weights, only for an entry still measured (no pinned revision), its MoE on Triton
# (the recipe for Blackwell desktops: the drafter's default fused MoE path is not built there)
ENTWURF_MOE = "triton"
VENVS = ("llm",)                 # $PREFIX/venv-<name>: venv-llm (install.sh --llm)
KV = ("fp8",)
LOGPROBS_MAX = 20                # top_logprobs an engine started here gives (--max-logprobs; System One in llm_tor.py)
ROLLEN = {"llm": ("modell", "engine_port", 31016), "sehen": ("sehen_modell", "sehen_port", 31017),   # config llm.*
          # the small helper model beside the language model (Dominik 2026-10-25 „1+2 und 3a b c d e“): fixed-answer
          # questions (System One) and short texts, started on demand by the LLM-Tor, never with tools
          "helfer": ("helfer_modell", "helfer_port", 31018)}
ANFRAGE_KEYS = ("chat_template_kwargs", "top_k")
# the only file kinds a model download takes: weights as safetensors, the rest is text; never *.bin/*.pt/*.pkl
ERLAUBT = ("*.safetensors", "*.json", "*.txt", "*.jinja", "*.model", "*.tiktoken", "*.md", "LICENSE*")
GEWICHTE = (".safetensors",)
# „Nur herunterladen“ (stage B1c): any public model, also the weight formats of sd.cpp, acestep.cpp and ONNX
ERLAUBT_LADEN = ERLAUBT + ("*.gguf", "*.onnx", "*.onnx_data")
GEWICHTE_LADEN = (".safetensors", ".gguf", ".onnx")
VERBOTEN = re.compile(r"(?i)\.(bin|pt|pth|pkl|pickle|ckpt|py|pyc|so|sh)$")
REPO, REV = hftoken.REPO, hftoken.REV      # a Hugging Face name, a pinned commit
ID = re.compile(r"^[a-z0-9][a-z0-9.-]{1,47}$")
PARSER = re.compile(r"^[a-z0-9_]{2,32}$")
QUANT = ("fp8", "modelopt_mixed")
CHAT = "/v1/chat/completions"   # the engine itself on its measuring port, never the panel's model (llm.py)
GESUND_S = 1200                  # an engine has this long to load (first start compiles kernels)
# the first start compiles CUDA kernels for the GB10 (FlashInfer, torch); unbounded it runs one compiler (cicc, about
# 6 GB each) per CPU core at once and fills the unified memory (Dominik 2026-10-15: OOM kill of cicc while measuring).
# The engine units and the measurement take these; the compiled kernels stay in the cache under HOME, so it is once.
KOMPILIEREN = {"MAX_JOBS": "4", "NVCC_THREADS": "1", "TORCHINDUCTOR_COMPILE_THREADS": "4"}
# Docker only on the model computer and only for a model engine (Dominik 2026-10-17 „1a 2a 3a“, Richtlinie Teil 1):
# a model whose engine needs a community image (vllm "docker": the recipe's name). The image is pinned by its digest,
# the container has no network at all (the engine answers on a Unix socket in its own folder, dockertor.py puts that
# on 127.0.0.1), the Hugging Face cache is read-only, the only writable folder is its own cache under STATE, no
# capabilities, no new privileges, the panel's user inside. The flags and settings come from the model card, fixed
# here; nothing of them comes from the panel or the model. Stage 1: measured only (wechsel_pruefen says "docker").
DOCKER = {"b12x": {
    "image": "eugr/spark-vllm-b12x@sha256:03a956544e9f9b4b7ba91690469fbe7848bdbef29a7d2e0f5788368467bb3595",
    "seit": "2026-11-05",        # the day this digest was pinned: the nightly "Pakete prüfen" names it after 90 days
    "umgebung": {"VLLM_PLE_TABLE_MEMORY": "disk", "B12X_DISK_BACKEND": "io_uring", "CUTE_DSL_ARCH": "sm_121a",
                 "SAFETENSORS_FAST_GPU": "1", "VLLM_WORKER_MULTIPROC_METHOD": "spawn", "VLLM_SSM_CONV_STATE_LAYOUT": "DS",
                 "VLLM_USE_AOT_COMPILE": "1", "VLLM_USE_MEGA_AOT_ARTIFACT": "1", "VLLM_USE_V2_MODEL_RUNNER": "1",
                 "B12X_POLICY_MODE": "auto", "VLLM_MXFP8_LM_HEAD": "1", "VLLM_B12X_MOE_FP4_LAYER_MAX_INPUT_SCALE": "w13",
                 "VLLM_B12X_MOE_FP4_FORCE_A16": "1", "B12X_W4A16_A4_PREFILL": "1",
                 "VLLM_ENGINE_READY_TIMEOUT_S": "3600",      # the first start loads and tunes for well over 10 minutes
                 # PyTorch keeps at most 95 % for itself and gives freed blocks back early: qwen38 v1.37.0 runs the same
                 # image with it and keeps 17-19 GiB free after loading (Dominik 2026-10-21 "1"; without it 0.1 GiB)
                 "PYTORCH_CUDA_ALLOC_CONF": "per_process_memory_fraction:0.95,garbage_collection_threshold:0.8"},
    "args": ["--dtype", "bfloat16", "--block-size", "16", "--load-format", "b12x", "--enable-prefix-caching",
             "--enable-chunked-prefill", "--mamba-cache-mode", "align", "--max-num-batched-tokens", "4096",
             "--gdn-decode-kernel", "b12x", "--linear-backend", "b12x", "--moe-backend", "b12x",
             "--mm-encoder-tp-mode", "data", "--compilation-config", '{"pass_config":{"fuse_act_quant":true}}'],
    "laden_s": 3600,
    # the b12x PLE table is read from disk with io_uring, which Docker's default seccomp profile blocks (tars
    # 2026-10-18: "io_uring initialization failed: Operation not permitted"): seccomp stays on with Docker's default
    # profile plus exactly io_uring_setup/enter/register, a file next to this one pinned by its SHA-256
    "seccomp": ("docker-seccomp-b12x.json", "6cc1a680ead8d595450e8b476c0c7624d6fa4aff655f0f95ebbc3b13c9a06cc3")}}
IMAGE = re.compile(r"^[a-z0-9][a-z0-9._/-]{0,127}@sha256:[0-9a-f]{64}$")
DOCKER_NAME = re.compile(r"^speech-spark-[a-z0-9-]{1,40}$")
DOCKER_ORDNER = os.path.join(STATE, "docker-modelle")   # <id>/cache (writable) and <id>/sock (the engine's socket)
DOCKER_SOCK = "/sock/engine.sock"                          # inside the container

# fixed German questions (TTFT and tokens per second), one tool call, two test pictures
FRAGEN = ("Erkläre in vier Sätzen, warum der Himmel blau ist.",
          "Schreib eine kurze, freundliche Mail an einen Nachbarn: Das Paket liegt bei mir, er kann es heute ab 18 Uhr holen.",
          "Fasse zusammen, was man beim Kauf eines gebrauchten Fahrrads prüfen sollte. Höchstens sechs Punkte.")
# a long fixed start (about 8k tokens, like the panel's tool list in front of every question) for the prefix cache:
# the first question with it is cold, the second warm; the run's own first line keeps an earlier run's cache out
VORLAUF = "\n".join(f"Regel {i}: Antworte kurz, freundlich und auf Deutsch, nenne nur Zahlen, die du geprüft hast, "
                     f"und frag nach, wenn etwas fehlt." for i in range(1, 261))
VORLAUF_FRAGE = "Nenne die Nummer der ersten Regel."
LANG = "Erzähl ausführlich, wie ein Leuchtturm funktioniert, von der Lampe bis zur Kennung. Etwa 300 Wörter."
# several answers at once, each after a long question of its own (about VORLAUF's 8k tokens), and one question of
# about LANG_ZIEL tokens; KONTEXT_ZIEL is the length the context room is counted in
PARALLEL = (2, 4)
LANG_ZIEL = 60000
KONTEXT_ZIEL = 65536
WERKZEUG = {"type": "function", "function": {
    "name": "wetter", "description": "Wettervorhersage für einen Ort",
    "parameters": {"type": "object", "properties": {"ort": {"type": "string"}, "tag": {"type": "string"}},
                   "required": ["ort"]}}}
WERKZEUG_FRAGE = "Wie wird das Wetter morgen in Hamburg?"
BILD_TEXT = ("RECHNUNG Nr. 4711", "Betrag: 23,50 EUR", "Datum: 14.10.2026")
BILD_TEXT_FRAGE = "Welche Rechnungsnummer und welcher Betrag stehen auf dem Bild? Antworte in einem Satz."
BILD_SZENE_FRAGE = "Welche zwei Formen siehst du und welche Farbe hat jede? Antworte kurz auf Deutsch."
BILD_MALEN = "Ein Leuchtturm an der Nordsee bei Sonnenuntergang"


class Fehler(ValueError):
    pass


# ---------------------------------------------------------------- catalog
def pruefe_eintrag(m):
    """The rules for one catalog entry; raises Fehler with a fixed word."""
    if not isinstance(m, dict):
        raise Fehler("eintrag")
    if not ID.match(str(m.get("id", ""))):
        raise Fehler("id")
    if m.get("art") not in ARTEN or m.get("engine") not in ENGINES or m.get("betrieb") not in BETRIEB:
        raise Fehler("art")
    if (not REPO.match(str(m.get("repo", ""))) or ".." in m["repo"]):
        raise Fehler("repo")
    if not (m.get("revision") == "" or REV.match(str(m.get("revision")))):
        raise Fehler("revision")
    name = m.get("name")
    if not isinstance(name, dict) or not all(isinstance(name.get(x), str) and name[x] for x in ("de", "en")):
        raise Fehler("name")
    for key in ("need_gib", "platte_gb"):
        if isinstance(m.get(key), bool) or not isinstance(m.get(key), (int, float)) or m[key] <= 0:
            raise Fehler(key)
    if not all(isinstance(m.get(x), bool) for x in ("gewerblich", "gemessen")):
        raise Fehler("schalter")
    if m["engine"] in ("sdcpp", "acestepcpp") and not isinstance(m.get("variante"), str):
        raise Fehler("variante")
    e = m.get("empfohlen", [])
    if not isinstance(e, list) or len(set(e)) != len(e) or not set(e) <= set(hardware.KLASSEN):
        raise Fehler("empfohlen")
    if "trust_remote_code" in json.dumps(m):
        raise Fehler("trust_remote_code")
    if m["engine"] == "vllm":
        _pruefe_vllm(m)
    return m


def _pruefe_vllm(m):
    """An engine started by this installation: only llm or sehen, its memory in GiB (whether it fits is a question of
    the computer: vllm_args, budget), only the known flags and request fields."""
    if m["art"] not in ROLLEN or m.get("messen") not in MESSEN:
        raise Fehler("art")
    g = m.get("gpu_gib")
    if isinstance(g, bool) or not isinstance(g, (int, float)) or not 1 <= g <= GPU_GIB_MAX or "anteil" in m:
        raise Fehler("gpu_gib")
    for key in ("kontext", "kontext_max"):
        k = m.get(key, m.get("kontext"))
        if isinstance(k, bool) or not isinstance(k, int) or not 2048 <= k <= 262144:
            raise Fehler("kontext")
    if m.get("kontext_max", m["kontext"]) < m["kontext"]:
        raise Fehler("kontext")
    if not all(isinstance(m.get(x), bool) for x in ("kann_sehen", "werkzeuge")):
        raise Fehler("schalter")
    if m["art"] == "sehen" and not m["kann_sehen"]:
        raise Fehler("sehen")
    if m["art"] == "helfer" and (m["kann_sehen"] or m["werkzeuge"]):     # the helper only sorts and writes short texts
        raise Fehler("helfer")
    v, q = m.get("vllm"), m.get("anfrage")
    if not isinstance(v, dict) or set(v) - set(VLLM_KEYS) or not isinstance(q, dict) or set(q) - set(ANFRAGE_KEYS):
        raise Fehler("felder")
    for key in ("reasoning_parser", "tool_call_parser"):
        if key in v and not PARSER.match(str(v[key])):
            raise Fehler(key)
    for key, hi in (("mtp", 8), ("max_seqs", 64), ("bilder_pro_frage", 8)):
        if key in v and (isinstance(v[key], bool) or not isinstance(v[key], int) or not 0 <= v[key] <= hi):
            raise Fehler(key)
    if "batched_tokens" in v and (isinstance(v["batched_tokens"], bool) or not isinstance(v["batched_tokens"], int)
                                  or not 2048 <= v["batched_tokens"] <= 32768):
        raise Fehler("batched_tokens")
    if "quantization" in v and v["quantization"] not in QUANT:
        raise Fehler("quantization")
    if "kv_cache_dtype" in v and v["kv_cache_dtype"] not in KV:
        raise Fehler("kv_cache_dtype")
    if v.get("venv", "llm") not in VENVS:
        raise Fehler("venv")
    if "docker" in v and (v["docker"] not in DOCKER or m["art"] != "llm" or "venv" in v):
        raise Fehler("docker")
    # the draft model: on an entry still measured its newest commit, on a pinned entry (an own recipe) its own pinned one
    er = v.get("entwurf_revision")
    if "entwurf" in v and (not isinstance(v["entwurf"], str) or not REPO.match(v["entwurf"]) or not v.get("mtp")
                           or "docker" in v or (bool(m["revision"]) != bool(er)) or (er and not REV.match(str(er)))):
        raise Fehler("entwurf")
    if er is not None and "entwurf" not in v:
        raise Fehler("entwurf")


def _aus_bildmodell(m):
    """A picture entry (engine sdcpp) or a music entry (acestepcpp) takes name, licence, memory, repository and disk
    size from bildmodell.VARIANTS or musikmodell.VARIANTS: the files with their checksums live there, and install.sh
    hands those files alone to the service user. An own entry (DATEI_ART) carries its own fields."""
    if m.get("eigen"):
        return m
    if m.get("engine") == "acestepcpp":
        import musikmodell
        v = musikmodell.VARIANTS.get(m.get("variante"))
        if v is None:
            raise Fehler("variante")
        return dict(m, name={"de": v["name"], "en": v["name"]}, lizenz=musikmodell.LICENSE, gewerblich=True,
                    need_gib=v["need_gib"], repo=v["dit"].repo, revision=v["dit"].revision,
                    platte_gb=musikmodell.disk_gb(m["variante"]))
    if m.get("rolle") == "bildpruefung":         # the picture check's file, commit and SHA-256 live in bildmodell.CHECKER
        import bildmodell
        return dict(m, repo=bildmodell.CHECKER.repo, revision=bildmodell.CHECKER.revision)
    if m.get("engine") != "sdcpp":
        return m
    import bildmodell
    v = bildmodell.VARIANTS.get(m.get("variante"))
    if v is None:
        raise Fehler("variante")
    return dict(m, name={"de": v["name"], "en": v["name"]}, lizenz=v["license"], gewerblich=v["commercial"],
                need_gib=v["need_gib"], repo=v["model"].repo, revision=v["model"].revision,
                platte_gb=bildmodell.disk_gb(m["variante"]))


def _aus_basis(m, davor):
    """A variant: the earlier entry named in "basis" with this entry's fields over it, vllm and anfrage merged."""
    if not isinstance(m, dict) or "basis" not in m:
        return m
    b = davor.get(m["basis"])
    if b is None or b.get("basis") or b["engine"] != "vllm":
        raise Fehler("basis")
    if not isinstance(m.get("vllm", {}), dict) or not isinstance(m.get("anfrage", {}), dict):
        raise Fehler("felder")
    # the recommendation belongs to the entry that names it, never to its variants
    return {**{k: x for k, x in b.items() if k != "empfohlen"}, **m, "vllm": {**b["vllm"], **m.get("vllm", {})},
            "anfrage": {**b["anfrage"], **m.get("anfrage", {})}}


def _alt_anteil(m):
    """An own entry saved before stage A (a share of the GB10's pool) as GiB: the same memory on the same computer."""
    if isinstance(m, dict) and "anteil" in m and "gpu_gib" not in m:
        a = m["anteil"]
        rest = {k: v for k, v in m.items() if k != "anteil"}
        return dict(rest, gpu_gib=round(a * hardware.BEZUG_GIB, 1)) if isinstance(a, (int, float)) and not isinstance(a, bool) else rest
    return m


def katalog(path=KATALOG, eigene=None):
    """{id: entry} from modelle.json; every entry checked, ids unique. Then the admin's own entries (stage E5,
    STATE/modelle-eigene.json, only with the shipped catalog): each checked by the same rules plus eigen_ok();
    one that fails is left out, so a broken file never breaks the catalog."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for m in data.get("modelle", []):
        m = _aus_bildmodell(_aus_basis(m, out))
        pruefe_eintrag(m)
        if m["id"] in out:
            raise Fehler("doppelt")
        out[m["id"]] = m
    if eigene is None and path == KATALOG:
        eigene = EIGENE
    # eigene: the file, or the list itself (from the model computer's Wärter, plan Raspberry-Pi split B4c)
    rows = eigene if isinstance(eigene, list) else (read_json(eigene, {}).get("modelle") or []) if eigene else []
    for m in rows[:EIGENE_MAX]:
        m = _alt_anteil(m)
        try:
            eigen_ok(m)
        except Fehler:
            continue
        if m["id"] not in out:
            out[m["id"]] = m
    return out


def eintrag(mid, kat=None):
    kat = katalog() if kat is None else kat
    if mid not in kat:
        raise Fehler("unbekannt")
    return kat[mid]


def zum_repo(repo, kat=None):
    """The entry of a Hugging Face repository (exact name), None when the catalog does not have it."""
    kat = katalog() if kat is None else kat
    return next((m for m in kat.values() if m["repo"] and m["repo"] == str(repo).rstrip("/")), None)


def need_gib(repo, default=8):
    """Unified memory a model needs while loaded (GiB, catalog), default for a repository the catalog lacks."""
    m = zum_repo(repo)
    return m["need_gib"] if m else default


SPRACH_ANTEIL_MAX = 0.5


def sprach_anteil(anteil, pool_gib=None):
    """The speech engines' memory shares (asr.engine_mem, tts.engine_mem_talker/_code2wav) are set for the reference
    pool, a DGX Spark (hardware.BEZUG_GIB): on a pool more than 10 % larger or smaller (a DGX Station's GPU) the share
    that gives the same GiB, so the engine keeps its KV cache and leaves the rest to the others; on a Spark unchanged.
    engine.sh starts with it (modelle.py anteil)."""
    pool_gib = hardware.profil()["pool_gib"] if pool_gib is None else pool_gib
    if not isinstance(anteil, (int, float)) or isinstance(anteil, bool) or not pool_gib or abs(pool_gib - hardware.BEZUG_GIB) <= 0.1 * hardware.BEZUG_GIB:
        return anteil
    return round(min(SPRACH_ANTEIL_MAX, anteil * hardware.BEZUG_GIB / pool_gib), 4)


def zur_variante(art, v, kat=None):
    """The entry of a picture variant or a small model's size (field "variante")."""
    kat = katalog() if kat is None else kat
    return next((m for m in kat.values() if m["art"] == art and v and m.get("variante") == v), None)


def aktiv(cfg, total_gib, kat=None):
    """The models the configuration runs now: [{id, art, gib, betrieb}], gib from the engines' memory shares where
    the configuration sets them (vLLM), else from the catalog."""
    kat = katalog() if kat is None else kat
    out = []

    def add(m, gib=None, betrieb=None):
        if m:
            out.append({"id": m["id"], "art": m["art"], "gib": round(float(gib if gib is not None else m["need_gib"]), 1),
                        "betrieb": betrieb or m["betrieb"]})
    chat = cfg.get("chat", {})
    own = cfg.get("llm", {})
    if own.get("enabled"):
        m = kat.get(own.get("modell"))
        m = _platz(m, cfg) if m and m["engine"] == "vllm" and m["art"] == "llm" else m
        add(m, m["gpu_gib"] + 1.5 if m and m["engine"] == "vllm" else None)
        if m and not m.get("kann_sehen"):
            add(kat.get(own.get("sehen_modell")), None, "bei_bedarf")
        add(kat.get(own.get("helfer_modell")), None, "bei_bedarf")
    a = cfg.get("asr", {})
    if a.get("enabled"):
        if a.get("recognizer") == "parakeet":
            add(kat.get("parakeet-primeline"))
        else:
            gib = sprach_anteil(a["engine_mem"], total_gib) * total_gib + 1.5 if a.get("backend") == "vllm" and "engine_mem" in a else None
            add(zum_repo(a.get("model"), kat), gib)
            if a.get("timestamps"):
                add(zum_repo(a.get("aligner_model"), kat))
    t = cfg.get("tts", {})
    if t.get("enabled"):
        omni = t.get("backend") == "vllm-omni" and "engine_mem_talker" in t
        gib = (sprach_anteil(t["engine_mem_talker"], total_gib) + sprach_anteil(t.get("engine_mem_code2wav", 0), total_gib)) * total_gib + 1.5 if omni else None
        add(zum_repo(t.get("model"), kat), gib)
        if t.get("voicedesign_enabled"):   # on demand (voicedesign_leerlauf_min > 0) like the image understanding
            add(zum_repo(t.get("voicedesign_model"), kat), gib, None if t.get("voicedesign_leerlauf_min", 5) == 0 else "bei_bedarf")
        if klon_noetig(t):                 # the own designed voices (stimmdesign.py): always loaded, only beside a non-Base main
            add(zum_repo(t.get("klon_model"), kat), gib, "resident")
    img = cfg.get("image", {})
    if img.get("enabled"):
        add(zur_variante("bild", img.get("variant"), kat) or zur_variante("bild", "4b-q8", kat))
        add(kat.get("nsfw-pruefung"))
    mus = cfg.get("music", {})
    if mus.get("enabled"):
        add(zur_variante("musik", mus.get("variant"), kat) or zur_variante("musik", "2b", kat))
    if chat.get("doc_semantic"):
        add(kat.get("e5-small"))
    if chat.get("rerank"):
        add(zur_variante("klein", chat.get("rerank_model"), kat) or zur_variante("klein", "klein", kat))
    return out


EIN_PLATZ = ("bild", "musik")     # loaded one after the other, never both at once (schwer.ARTEN, the queue for pictures and music)
def budget(cfg, total_gib, kat=None, profil=None):
    """The memory budget (plan „Speicher-Budget“): fixed = the resident models + system + reserve; on demand = the
    models loaded when needed. "alle" when all of them fit at once, "ein_platz" when only one on-demand model fits
    beside the fixed ones (they then run one after the other through vorrang), "zu_knapp" when not even that fits.
    A fixed rule from numbers; the model decides nothing. profil (hardware.py, the model computer's): what the system
    takes beside the models, and on a computer whose GPU has its own memory (DGX Station) the CPU models do not count
    in the GPU's pool total_gib."""
    kat = katalog() if kat is None else kat
    profil = profil or hardware.profil()
    teile = aktiv(cfg, total_gib, kat)
    if not profil["gemeinsam"]:
        teile = [x for x in teile if (kat.get(x["id"]) or {}).get("engine") != "onnx-cpu"]
    system = profil["system_gib"]
    reserve = float(cfg.get("memory", {}).get("reserve_gib", 10))
    fest = round(sum(x["gib"] for x in teile if x["betrieb"] == "resident"), 1)
    # pictures and music share one place (Dominik 2026-10-18 „immer nur ein Modell, beide nicht gleichzeitig“):
    # the bigger of the two counts, never both
    bedarf = [x["gib"] for x in teile if x["betrieb"] == "bei_bedarf" and x["art"] not in EIN_PLATZ]
    bedarf += [max(x["gib"] for x in teile if x["betrieb"] == "bei_bedarf" and x["art"] in EIN_PLATZ)] \
        if any(x["betrieb"] == "bei_bedarf" and x["art"] in EIN_PLATZ for x in teile) else []
    frei = round(total_gib - system - reserve - fest, 1)
    if frei >= sum(bedarf):
        regel = "alle"
    elif frei >= max(bedarf, default=0):
        regel = "ein_platz"
    else:
        regel = "zu_knapp"
    return {"gesamt": round(total_gib, 1), "system": system, "reserve": reserve, "fest": fest,
            "bedarf": round(sum(bedarf), 1), "bedarf_max": round(max(bedarf, default=0), 1), "frei": frei,
            "regel": regel, "teile": teile, "ein_platz": list(EIN_PLATZ)}


def wahl(art, kat=None):
    """The entries install.sh offers for a kind, in catalog order (field "wahl" = the install's short key)."""
    if art not in ("asr", "tts", "bild", "musik"):
        raise Fehler("art")
    kat = katalog() if kat is None else kat
    return [m for m in kat.values() if m["art"] == art and m.get("wahl")]


def wahl_zeilen(art, kat=None):
    """The numbered lines of install.sh's question for one kind (English, like the install)."""
    out = []
    for i, m in enumerate(wahl(art, kat), 1):
        text = (m.get("text") or {}).get("en", "")
        if art == "musik":
            out.append(f"  {i}) {m['name']['en']:<32} ~{m['platte_gb']:g} GB disk, ~{m['need_gib']:g} GiB while making "
                       f"music, {m['lizenz']}{' (' + text + ')' if text else ''}")
        elif art == "bild":
            extra = "" if m["gewerblich"] else " (private use only)"
            extra += f" ({text})" if text and text != "private use only" else ""
            out.append(f"  {i}) {m['name']['en']:<24} ~{m['platte_gb']:g} GB disk, ~{m['need_gib']:g} GiB while painting, "
                       f"{m['lizenz']}{extra}")
        else:
            out.append(f"  {i}) {m['name']['en']:<26} {text + ', ' if text else ''}~{m['need_gib']:g} GiB")
    return out


def messliste(was, kat=None):
    """The ids to measure, in catalog order: was = words llm, sehen, helfer (the entries marked "immer"), qwen36
    (Qwen3.6 35B A3B NVFP4 with and without MTP), flash (Qwen3.8 Flash Next in Docker, measured only on request), gemma4 and gemma4mtp (Gemma 4 26B A4B NVFP4, the second with its draft model, on request), gemma4nv (NVIDIA's own
    NVFP4 of it with the draft model and 16384 tokens per step, on request);
    no word means llm and sehen. Only models that run or were measured stay in the catalog (Dominik 2026-11-11)."""
    kat = katalog() if kat is None else kat
    was = list(was) or ["llm", "sehen"]
    wunsch = {"qwen36": ("qwen36-35b-a3b-nvfp4", "qwen36-35b-a3b-nvfp4-ohne-mtp"),     # Dominik 2026-10-18 „ja 1“
              "flash": ("qwen38-flash-next-fp4",),     # Docker; share 0.65 never started (tars 2026-10-21)
              "gemma4": ("gemma4-26b-a4b-nvfp4",), "gemma4mtp": ("gemma4-26b-a4b-nvfp4-mtp",),
              "gemma4nv": ("gemma4-26b-a4b-nvidia-mtp",)}     # Dominik 2026-11-15 „1 und 2“     # Dominik 2026-11-13 „1“: a candidate, out again if it loses
    wunsch.update({i: (i,) for i, m in kat.items() if m.get("eigen") or docker_bild(m)})   # an own model by its id
    if any(w not in ("llm", "sehen", "helfer") and w not in wunsch for w in was):
        raise Fehler("was")
    ids = [i for x in was for i in wunsch.get(x, ())]
    return [i for i, m in kat.items() if m["engine"] == "vllm" and (i in ids or (m["art"] in was and m["messen"] == "immer"))]


def vllm_args(m, port=MESS_PORT, revision="", mtp=True, uds="", pool_gib=None):
    """The arguments after `vllm serve`: only from the catalog's checked fields, never trust_remote_code, always
    on 127.0.0.1 (an engine in Docker: only on its Unix socket uds, and only there). revision may stand in only for
    an entry without one (a measurement after the download)."""
    pruefe_eintrag(m)
    if m["engine"] != "vllm":
        raise Fehler("engine")
    if bool(m["vllm"].get("docker")) != bool(uds) or uds not in ("", DOCKER_SOCK):
        raise Fehler("docker")
    rev = m["revision"] or revision
    if not REV.match(rev or "") or (m["revision"] and revision and revision != m["revision"]):
        raise Fehler("revision")
    if isinstance(port, bool) or not isinstance(port, int) or not 31000 <= port <= 31099:
        raise Fehler("port")
    anteil = m["gpu_gib"] / (pool_gib or hardware.profil()["pool_gib"])     # GiB → this computer's share
    if anteil > ANTEIL_MAX:
        raise Fehler("budget")
    v = m["vllm"]
    a = [m["repo"], "--revision", rev, *(["--uds", uds] if uds else ["--host", "127.0.0.1", "--port", str(port)]),
         "--served-model-name", m["id"], "--max-model-len", str(m["kontext"]),
         "--gpu-memory-utilization", f"{anteil:.2f}", "--max-num-seqs", str(v.get("max_seqs", 8)),
         "--generation-config", "vllm", "--no-enable-flashinfer-autotune",
         "--disable-uvicorn-access-log",   # stats stay on: /metrics counts the MTP and prefix cache hits
         # usage.prompt_tokens_details.cached_tokens: the panel shows how much of a question came from the prefix cache
         # (chat.timing_lines, verbrauch.py); the cache itself is on by default in vLLM V1
         "--enable-prompt-tokens-details"]
    if v.get("quantization"):
        a += ["--quantization", v["quantization"]]
    if v.get("kv_cache_dtype"):
        a += ["--kv-cache-dtype", v["kv_cache_dtype"]]
    if v.get("batched_tokens"):      # more of a long question per step: the first word comes sooner (Dominik 2026-11-15)
        a += ["--max-num-batched-tokens", str(v["batched_tokens"])]
    if v.get("reasoning_parser"):
        a += ["--reasoning-parser", v["reasoning_parser"]]
    if v.get("tool_call_parser"):
        a += ["--tool-call-parser", v["tool_call_parser"], "--enable-auto-tool-choice"]
    if m["kann_sehen"]:      # a text-only model gets no picture flag at all
        a += ["--limit-mm-per-prompt.image", str(v.get("bilder_pro_frage", 2))]
    if mtp and v.get("mtp") and v.get("entwurf"):
        spec = {"model": v["entwurf"], "num_speculative_tokens": v["mtp"], "moe_backend": ENTWURF_MOE}
        if v.get("entwurf_revision"):
            spec["revision"] = v["entwurf_revision"]
        a += ["--speculative-config", json.dumps(spec)]
    elif mtp and v.get("mtp"):
        a += ["--speculative-config", json.dumps({"method": "mtp", "num_speculative_tokens": v["mtp"]})]
    return a + (DOCKER[v["docker"]]["args"] if uds else [])


def docker_bild(m):
    """The pinned image of an entry that runs in Docker, "" for every other one."""
    d = DOCKER.get((m.get("vllm") or {}).get("docker")) if m["engine"] == "vllm" else None
    if d is None:
        return ""
    if not IMAGE.match(d["image"]):
        raise Fehler("docker")
    return d["image"]


def _id_nr(x):
    if isinstance(x, bool) or not isinstance(x, int) or not 1 <= x <= 65533:
        raise Fehler("nutzer")
    return str(x)


def docker_args(m, revision, name, uid, gid, mtp=True, hf_home=None, ordner=None):
    """The arguments after `docker` for an entry with a recipe (DOCKER): `run` of the pinned image, no network, only
    the panel's user, no capabilities, the Hugging Face cache read-only, its own cache and socket folders, the card's
    settings, then `vllm serve` with vllm_args() on the socket. Root runs it (speech-spark.sh mess_docker)."""
    bild = docker_bild(m)
    if not bild:
        raise Fehler("docker")
    if not DOCKER_NAME.match(str(name)):
        raise Fehler("name")
    d = DOCKER[m["vllm"]["docker"]]
    profil = seccomp_profil(d)
    hf = os.path.realpath(hf_wurzel(hf_home))
    base = os.path.join(os.path.realpath(ordner or DOCKER_ORDNER), m["id"])
    umgebung = {"HF_HOME": "/hf", "HOME": "/cache", "HF_HUB_OFFLINE": "1", "VLLM_NO_USAGE_STATS": "1", "DO_NOT_TRACK": "1",
                **KOMPILIEREN, **d["umgebung"]}
    a = ["run", "--rm", "--name", name, "--network", "none", "--gpus", "all", "--user", f"{_id_nr(uid)}:{_id_nr(gid)}",
         "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
         *(["--security-opt", f"seccomp={profil}"] if profil else []), "--shm-size", "16g",
         "--ulimit", "memlock=-1", "--ulimit", "stack=67108864",
         "-v", f"{hf}:/hf:ro", "-v", f"{base}/cache:/cache", "-v", f"{base}/sock:/sock"]
    for k, v in umgebung.items():
        a += ["-e", f"{k}={v}"]
    return a + ["--entrypoint", "vllm", bild, "serve"] + vllm_args(m, MESS_PORT, revision, mtp, uds=DOCKER_SOCK)


def seccomp_profil(d):
    """The path of a recipe's own seccomp profile ("" = Docker's default), only when the file is unchanged."""
    if "seccomp" not in d:
        return ""
    name, sha = d["seccomp"]
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    if not re.fullmatch(r"docker-seccomp-[a-z0-9]+\.json", name):
        raise Fehler("seccomp")
    try:
        ok = _datei_hash(path, "sha256") == sha
    except OSError:
        ok = False
    if not ok:
        raise Fehler("seccomp")
    return path


def laden_frist(m):
    """Seconds an engine has to load: the recipe's for one in Docker, else GESUND_S."""
    return DOCKER[m["vllm"]["docker"]]["laden_s"] if docker_bild(m) else GESUND_S


def venv(m):
    """The venv folder name an entry's engine runs from ($PREFIX/venv-<name>)."""
    return m["vllm"].get("venv", "llm") if m["engine"] == "vllm" else ""


def fest_revision(m, messung=None):
    """The commit an engine of this installation starts: the catalog's, else the one a successful measurement
    downloaded and checked (an entry still open is pinned by `modelle messen`, never by a newer download)."""
    if m["revision"]:
        return m["revision"]
    messung = read_json(MESSUNG, {}) if messung is None else messung
    r = (messung.get("modelle") or {}).get(m["id"]) or {}
    rev = r.get("revision", "") if r.get("ok") else ""
    if not REV.match(rev):
        raise Fehler("revision")
    return rev


# Zustand → Modelle „Lange Gespräche“ (Dominik 2026-10-17): the own language model's context store as fixed choices,
# (extra memory in GiB, longest question in tokens; None = the catalog's). It is one pool: about 15 GiB hold 4
# conversations of 64K or one of 256K (Qwen3.8 NVFP4 on tars: 7.7 GiB for 131K, the KV cache already in FP8)
PLATZ = {"standard": (0.0, None), "4x64k": (8.4, 65536), "1x256k": (8.4, 262144)}
PLATZ_NAMEN = {"standard": ("Standard: 1 Gespräch mit 128K oder 2 mit 64K", "Standard: 1 conversation of 128K or 2 of 64K"),
               "4x64k": ("4 Gespräche gleichzeitig mit je 64K", "4 conversations at once of 64K each"),
               "1x256k": ("1 sehr langes Gespräch mit 256K", "1 very long conversation of 256K")}


def mit_platz(m, platz):
    """The language model's entry with the context store llm.platz picks; Fehler when the choice or the model does not
    allow it (a longer context than the model knows: kontext_max)."""
    if platz in (None, "standard"):
        return m
    if platz not in PLATZ or m["engine"] != "vllm" or m["art"] != "llm":
        raise Fehler("platz")
    plus, kontext = PLATZ[platz]
    if kontext > m.get("kontext_max", m["kontext"]):
        raise Fehler("kontext")
    return dict(m, gpu_gib=round(m["gpu_gib"] + plus, 1), kontext=kontext)


def _platz(m, cfg):
    """mit_platz for the engine that starts: a choice this model does not allow (after a switch) counts as standard."""
    try:
        return mit_platz(m, cfg.get("llm", {}).get("platz"))
    except Fehler:
        return m


def platz_pruefen(platz, cfg, total_gib, kat=None, profil=None):
    """The fixed rules for „Lange Gespräche“: a known choice, the own language model on, one the model allows, not the one set, and
    the budget must not end up too tight. Returns the entry as it would start; raises Fehler with a fixed word."""
    if platz not in PLATZ:
        raise Fehler("platz")
    c = cfg.get("llm", {})
    if not c.get("enabled"):
        raise Fehler("aus")
    neu = mit_platz(eintrag(c.get("modell"), kat), platz)
    if (c.get("platz") or "standard") == platz:
        raise Fehler("schon")
    probe = json.loads(json.dumps(cfg))
    probe.setdefault("llm", {})["platz"] = platz
    if budget(probe, total_gib, kat, profil)["regel"] == "zu_knapp":
        raise Fehler("budget")
    return neu


def platz_wahl(cfg, total_gib, kat=None, profil=None):
    """For the page: the choices with their extra memory and why one is not possible (a fixed word, "" when it is)."""
    c = cfg.get("llm", {})
    m = (kat or katalog()).get(c.get("modell"))
    out = []
    for p, (plus, _) in PLATZ.items():
        try:
            if m is None:
                raise Fehler("aus")
            platz_pruefen(p, cfg, total_gib, kat, profil)
            nein = ""
        except Fehler as e:
            nein = str(e)
        out.append({"id": p, "name": PLATZ_NAMEN[p], "plus_gib": plus, "nein": nein})
    return {"jetzt": c.get("platz") or "standard", "wahl": out}


def rolle(art, cfg, kat=None):
    """(entry, port) of the engine speech-spark-llm (art llm) or speech-spark-sehen (art sehen), from config llm.*."""
    if art not in ROLLEN:
        raise Fehler("art")
    feld, port_feld, port_std = ROLLEN[art]
    c = cfg.get("llm", {})
    m = eintrag(c.get(feld), kat)
    port = c.get(port_feld, port_std)
    if m["engine"] != "vllm" or m["art"] != art or isinstance(port, bool) or not isinstance(port, int) or port == MESS_PORT and art != "llm":
        raise Fehler("art")
    if docker_bild(m):        # stage 1: an engine in Docker is measured only, never started by speech-spark-llm
        raise Fehler("docker")
    return (_platz(m, cfg) if art == "llm" else m), port


def signatur(art, cfg, messung=None, kat=None):
    """What speech-spark-llm / -sehen start from, as 16 hex: its catalog entry (own entries included) and its start
    arguments (port, pinned commit, a new option such as --enable-prompt-tokens-details). install.sh restarts the engine only when this changed, so a new music or image model in the catalog does
    not load the language model again (that load took many minutes, tars 2026-10-16)."""
    m, port = rolle(art, cfg, kat)
    roh = json.dumps([m, vllm_args(m, port, fest_revision(m, messung)), LOGPROBS_MAX], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(roh.encode()).hexdigest()[:16]


def start_args(art, cfg, messung=None, kat=None, hf_home=None):
    """The arguments after `vllm serve` for speech-spark-llm / speech-spark-sehen (engine.sh llm|sehen): the
    pinned commit, its files checked (kinds and links; the hashes were checked at the download), offline."""
    m, port = rolle(art, cfg, kat)
    rev = fest_revision(m, messung)
    pruefen(hf_ordner(m, hf_home), rev, hashes=False)
    zeiger(hf_ordner(m, hf_home), rev)
    return vllm_args(m, port, rev) + ["--max-logprobs", str(LOGPROBS_MAX)]


def start_merken(art, cfg):
    """Startprotokoll (stage B1d): engine.sh starts art with what start_args gave; kept by llmstart.merken with the
    signature install.sh compares. Never stops the start: a full disk only loses the line in the protocol."""
    import llmstart
    try:
        m, _ = rolle(art, cfg)
        llmstart.merken(art, m["id"], signatur(art, cfg), m.get("gpu_gib", 0), m.get("kontext", 0),
                        hardware.profil()["id"])
    except (OSError, ValueError, Fehler):
        print(f"modelle: startprotokoll {art} fehler", file=sys.stderr, flush=True)


def abweichung(art, cfg, kat=None, path=None):
    """Rezept-Abgleich (stage B1b, alzeo idea 1): the engine of art started with other settings than its catalog entry
    gives now (an update changed the entry, a start before it, a recipe saved while it was off). False when nothing
    was started here or the kind has no model."""
    import llmstart
    e = llmstart.letzter(art) if path is None else llmstart.letzter(art, path)
    if not e:
        return False
    try:
        return e.get("sig") != signatur(art, cfg, kat=kat)
    except (Fehler, KeyError, ValueError):
        return False


def neustart_anfragen(cfg, starten, laeuft=False, kat=None, path=None):
    """„Neu starten“ on the running language model's card: only when it runs with other settings (abweichung); the
    wish for root (art neustart), then starten() starts WECHSEL_UNIT. Raises Fehler (laeuft, schon, start)."""
    if laeuft:
        raise Fehler("laeuft")
    if not abweichung("llm", cfg, kat, path):
        raise Fehler("schon")
    wunsch_schreiben("neustart", "llm")
    if not starten():
        raise Fehler("start")


# ---------------------------------------------------------------- files in the Hugging Face cache
def hf_wurzel(hf_home=None):
    """The Hugging Face folder of this computer (HF_HOME, else the library's own default)."""
    return hf_home or os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface")


def hf_ordner(m, hf_home=None):
    return os.path.join(hf_wurzel(hf_home), "hub", "models--" + m["repo"].replace("/", "--"))


def _datei_hash(path, algo, kopf=b""):
    h = hashlib.new(algo)
    h.update(kopf)
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def pruefen(ordner, rev, hashes=True, gewichte=GEWICHTE):
    """Checks one snapshot in a Hugging Face cache folder: every entry a link into blobs/ (which may link once more
    into the shared hub/blobs/<2 hex>/ of newer huggingface_hub), no file kind outside
    ERLAUBT, every blob equal to its name (64 hex = SHA-256 of a large file, 40 hex = git blob hash of a small
    one; hashes=False skips only this last step, for the start of an engine after the download was checked).
    Returns (files, bytes); raises Fehler with a fixed word."""
    if not REV.match(rev or ""):
        raise Fehler("revision")
    snap = os.path.join(ordner, "snapshots", rev)
    blobs = os.path.realpath(os.path.join(ordner, "blobs"))
    # newer huggingface_hub keeps large files once for all models in hub/blobs/<2 hex>/ and links the model's blob there
    gemeinsam = os.path.realpath(os.path.join(ordner, "..", "blobs"))
    if not os.path.isdir(snap) or os.path.islink(snap):
        raise Fehler("fehlt")
    n = size = 0
    weights = False
    for root, dirs, files in os.walk(snap):
        for d in dirs:
            if os.path.islink(os.path.join(root, d)):
                raise Fehler("link")
        for name in files:
            p = os.path.join(root, name)
            if VERBOTEN.search(name):
                raise Fehler("dateiart")
            if not os.path.islink(p):
                raise Fehler("link")
            erst = os.path.join(root, os.readlink(p))           # one step: the model's blobs/<hash>
            blob = os.path.basename(erst)
            if os.path.realpath(os.path.dirname(erst)) != blobs:
                raise Fehler("link")
            ziel = os.path.realpath(erst)
            weiter = os.path.islink(os.path.join(blobs, blob))
            if weiter and os.path.dirname(os.path.dirname(ziel)) != gemeinsam:
                raise Fehler("link")
            if not weiter and ziel != os.path.join(blobs, blob):
                raise Fehler("link")
            if not os.path.isfile(ziel) or os.path.islink(ziel):
                raise Fehler("link")
            if not hashes:
                ok = bool(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", blob))
            elif re.fullmatch(r"[0-9a-f]{64}", blob):
                ok = _datei_hash(ziel, "sha256") == blob
            elif re.fullmatch(r"[0-9a-f]{40}", blob):
                ok = _datei_hash(ziel, "sha1", b"blob %d\0" % os.path.getsize(ziel)) == blob
            else:
                ok = False
            if not ok:
                raise Fehler("hash")
            weights = weights or name.endswith(gewichte)
            n += 1
            size += os.path.getsize(ziel)
    if not weights:
        raise Fehler("gewichte")
    return n, size


def _aufraeumen(ordner, rev, erlaubt=ERLAUBT):
    """Takes out of one cached snapshot the links of file kinds a download never takes (VERBOTEN, or outside
    ERLAUBT): a cache filled before the commits were pinned (a whole repository from "main", with *.py or *.bin) would
    otherwise fail the check on every update, as a new download never removes a file (security review of V01.0.785).
    Only links inside snapshots/<rev> go; their blobs and every plain file stay. Returns how many went."""
    import fnmatch
    snap = os.path.join(ordner, "snapshots", rev)
    if not REV.match(rev or "") or not os.path.isdir(snap) or os.path.islink(snap):
        return 0
    n = 0
    for root, _, files in os.walk(snap):
        for name in files:
            p = os.path.join(root, name)
            rel = os.path.relpath(p, snap)
            if os.path.islink(p) and (VERBOTEN.search(name) or not any(fnmatch.fnmatch(rel, e) for e in erlaubt)):
                os.unlink(p)
                n += 1
    return n


def _laden(repo, rev, ordner, erlaubt=ERLAUBT, gewichte=GEWICHTE):
    """One repository's commit in the cache, checked; downloads only the erlaubt kinds when the check fails."""
    if rev:
        try:
            pruefen(ordner, rev, gewichte=gewichte)
            zeiger(ordner, rev)
            return rev
        except Fehler:
            weg = _aufraeumen(ordner, rev, erlaubt)
            if weg:
                print(f"modelle: {weg} alte dateien entfernt", flush=True)
    from huggingface_hub import snapshot_download
    # the admin's token only to huggingface.co (faster, and models whose terms the admin accepted); False: never a
    # token file of the library's own
    path = snapshot_download(repo, revision=rev or None, allow_patterns=list(erlaubt), token=hftoken.token() or False)
    commit = os.path.basename(os.path.normpath(path))
    if rev and commit != rev:
        raise Fehler("revision")
    pruefen(ordner, commit, gewichte=gewichte)
    zeiger(ordner, commit)
    return commit


def zeiger(ordner, rev):
    """Makes the checked, pinned commit of a cached repository what a loader without a revision finds offline
    (vllm-omni's omni_snapshot_download asks for the repository without one):
    - refs/main points at the commit. snapshot_download with a commit writes no refs/main; with HF_HUB_OFFLINE the
      loader then stopped (LocalEntryNotFoundError, speech-spark-tts-design restarted every 30 s on tars 2026-10-23).
    - the cached tree listing of the commit (trees/<commit>.json) goes. It lists every file of the repository, also
      the kinds the download never takes (ERLAUBT), and offline huggingface_hub then calls the snapshot incomplete
      (IncompleteSnapshotError, ".gitattributes missing", tars 2026-10-24). Without it the library trusts the folder;
      pruefen has checked every file in it. Online the next download writes it again, and this runs after it.
    Only a commit of 40 hex whose snapshot exists; refs/main written only when it differs, through a temporary file.
    A file it may not change (e.g. left by root) only gets a log line, the start goes on. Returns whether anything
    changed."""
    if not REV.match(rev or "") or not os.path.isdir(os.path.join(ordner, "snapshots", rev)):
        raise Fehler("revision")
    neu = False
    try:
        liste = os.path.join(ordner, "trees", rev + ".json")
        if os.path.islink(liste) or os.path.isfile(liste):
            os.unlink(liste)
            neu = True
        refs = os.path.join(ordner, "refs")
        ziel = os.path.join(refs, "main")
        try:
            with open(ziel) as f:
                if f.read().strip() == rev and not os.path.islink(ziel):
                    return neu
        except OSError:
            pass
        os.makedirs(refs, exist_ok=True)
        tmp = ziel + ".neu"
        with open(tmp, "w") as f:
            f.write(rev)
        os.replace(tmp, ziel)
        return True
    except OSError as e:
        # never a reason to keep a checked model from starting (e.g. a file left by root): the start goes on as before
        print(f"modelle: zeiger fehlgeschlagen {type(e).__name__}", flush=True)
        return neu


def fest(repo, kat=None):
    """The catalog entry of a speech, search or picture check model with its pinned commit (Dominik 2026-10-18,
    Abgleich sichere KI-Architektur Punkt 2: every model on a fixed commit like the language models). Raises Fehler
    for a repository the catalog lacks or that has no pinned commit."""
    m = zum_repo(repo, kat)
    if not m or not REV.match(m["revision"] or ""):
        raise Fehler("revision")
    return m


def lokal(repo, hf_home=None, kat=None):
    """The checked folder of a pinned speech model for asr_server.py / tts_server.py: its pinned commit in the cache,
    fetched when missing (only the ERLAUBT kinds, e.g. after another voice was chosen in the panel), every file a
    checked kind and link and equal to its hash (security review of V01.0.785), like engine.sh before vLLM starts."""
    m = fest(repo, kat)
    vorbereiten(m, hf_home)
    return os.path.join(hf_ordner(m, hf_home), "snapshots", m["revision"])


# the switches the Hugging Face libraries read: set, they never ask the internet
OHNE_NETZ = {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1"}


def ohne_netz():
    """From here on this process loads only from its own disk (Dominik 2026-10-23, offline): asr_server.py and
    tts_server.py call it after modelle.lokal() fetched and checked every file and before they import the model's
    library, so its from_pretrained never asks the Hub (no lookup that hangs without the internet, no file beside the
    checked commit). Set in the environment for libraries imported later and in those already imported (they read it
    once at import). The engines do the same in engine.sh (HF_HUB_OFFLINE), test_offline checks every loader."""
    os.environ.update(OHNE_NETZ)
    hub = sys.modules.get("huggingface_hub.constants")
    if hub is not None:
        hub.HF_HUB_OFFLINE = True
    tf = sys.modules.get("transformers.utils.hub")
    if tf is not None and hasattr(tf, "_is_offline_mode"):
        tf._is_offline_mode = True


def vorbereiten(m, hf_home=None):
    """Makes sure the weights are in the cache (download only the ERLAUBT kinds) and checks them. Returns the
    commit. A pinned revision is fetched exactly; an empty one takes the newest commit (only to measure)."""
    commit = _laden(m["repo"], m["revision"], hf_ordner(m, hf_home))
    entwurf = (m.get("vllm") or {}).get("entwurf") if m["engine"] == "vllm" else None
    if entwurf:      # the draft model beside it: its pinned commit (an own recipe), else the newest
        _laden(entwurf, m["vllm"].get("entwurf_revision", ""), hf_ordner({"repo": entwurf}, hf_home))
    return commit


# ---------------------------------------------------------------- measuring
def _post(port, path, body, timeout=300, key=""):
    h = {"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})}
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", json.dumps(body).encode(), h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _get(port, path, timeout=5):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _body(m, messages, max_tokens, **extra):
    return {"model": m["id"], "messages": messages, "max_tokens": max_tokens, "temperature": 0.7, "top_p": 0.8,
            **m["anfrage"], **extra}


def stream_messen(port, body, timeout=300, now=time.monotonic, usage=None):
    """One streamed answer: (seconds to the first token, tokens, tokens per second after the first); usage (a dict)
    takes the engine's token counts."""
    body = dict(body, stream=True, stream_options={"include_usage": True})
    req = urllib.request.Request(f"http://127.0.0.1:{port}{CHAT}", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    t0, first, tokens = now(), None, 0
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:") or line == "data: [DONE]":
                continue
            d = json.loads(line[5:])
            for c in d.get("choices") or []:
                if first is None and (c.get("delta") or {}).get("content"):
                    first = now()
            if d.get("usage"):
                tokens = int(d["usage"].get("completion_tokens") or 0)
                if usage is not None:
                    usage.update(prompt_tokens=int(d["usage"].get("prompt_tokens") or 0), completion_tokens=tokens)
    end = now()
    if first is None:
        raise Fehler("leer")
    return round(first - t0, 2), tokens, round(tokens / max(end - first, 1e-3), 1)


def spec_zaehler(text):
    """(accepted, drafted) speculative tokens from vLLM's /metrics text, 0 when absent."""
    def summe(name):
        return sum(float(x) for x in re.findall(rf"^vllm:{name}(?:{{[^}}]*}})? ([0-9.e+]+)$", text, re.M))
    return summe("spec_decode_num_accepted_tokens_total"), summe("spec_decode_num_draft_tokens_total")


def cache_zaehler(text):
    """(hits, queries) of vLLM's prefix cache in tokens from /metrics, 0 when absent."""
    def summe(name):
        return sum(float(x) for x in re.findall(rf"^vllm:{name}(?:{{[^}}]*}})? ([0-9.e+]+)$", text, re.M))
    return summe("prefix_cache_hits_total"), summe("prefix_cache_queries_total")


def cache_messen(m, port, zeit, log=print):
    """The prefix cache: the same long question twice, first word cold and warm and the share of the second one's
    prompt that came from the cache (numbers only; the answers are dropped)."""
    msgs = [{"role": "system", "content": f"Messlauf {zeit}\n{VORLAUF}"}, {"role": "user", "content": VORLAUF_FRAGE}]
    try:
        vorher = cache_zaehler(_get(port, "/metrics"))
    except Exception:
        vorher = None
    kalt = stream_messen(port, _body(m, msgs, 16))[0]
    try:
        mitte = cache_zaehler(_get(port, "/metrics"))
    except Exception:
        mitte = None
    warm = stream_messen(port, _body(m, msgs, 16))[0]
    r = {"erste_kalt_s": kalt, "erste_warm_s": warm}
    try:
        nach = cache_zaehler(_get(port, "/metrics"))
        if vorher is not None and mitte is not None and nach[1] > mitte[1]:
            r["zwischenspeicher"] = round((nach[0] - mitte[0]) / (nach[1] - mitte[1]), 2)
    except Exception:
        pass
    anteil = f"{int(r['zwischenspeicher'] * 100)} %" if "zwischenspeicher" in r else "unbekannt"
    log(f"modelle: messung {m['id']} zwischenspeicher {anteil}, erste kalt {kalt} s, warm {warm} s")
    return r


def kv_platz(text):
    """Tokens the engine's context store holds (num_gpu_blocks × block_size of vllm:cache_config_info), None when
    absent; for a model with linear attention layers (Qwen3.8) an estimate."""
    z = re.search(r"^vllm:cache_config_info\{([^}]*)\}", text, re.M)
    if not z:
        return None
    f = dict(re.findall(r'(\w+)="([^"]*)"', z.group(1)))
    try:
        return int(f["num_gpu_blocks"]) * int(f["block_size"])
    except (KeyError, ValueError):
        return None


def _je_vorlauf(m, port):
    """Tokens of VORLAUF by the engine's own /tokenize (8000 when it does not answer: then fewer copies, never more)."""
    try:
        n = int(_post(port, "/tokenize", {"model": m["id"], "prompt": VORLAUF}, timeout=60)["count"])
        return n if n > 0 else 8000
    except Exception:
        return 8000


def langer_text(kopf, kopien):
    """A long fixed question start: VORLAUF `kopien` times; kopf (run, kind, number) keeps each one out of the
    prefix cache of the others."""
    return kopf + "\n" + "\n".join(f"Teil {i + 1}\n{VORLAUF}" for i in range(kopien))


def _gleichzeitig(port, bodies, timeout=600):
    """The streamed answers at once: one (first, tokens, tok/s) each, or an exception's word."""
    out = [None] * len(bodies)

    def eins(i):
        try:
            out[i] = stream_messen(port, bodies[i], timeout)
        except Exception as e:
            out[i] = str(e) if isinstance(e, Fehler) else type(e).__name__.lower()[:24]
    t = [threading.Thread(target=eins, args=(i,), daemon=True) for i in range(len(bodies))]
    for x in t:
        x.start()
    for x in t:
        x.join(timeout + 30)
    return out


def parallel_messen(m, port, zeit, log=print):
    """Several answers at once after long questions of their own, one question of about LANG_ZIEL tokens and the
    context room (numbers only; the answers are dropped). A part that fails gives its word, the rest still runs."""
    mid, r = m["id"], {}
    try:
        platz = kv_platz(_get(port, "/metrics"))
    except Exception:
        platz = None
    if platz:
        r["kv_tokens"] = platz
        r["platz_64k"] = platz // KONTEXT_ZIEL
        log(f"modelle: messung {mid} gespraechsspeicher {platz} tokens, platz fuer {r['platz_64k']} mal 64k")
    for n in PARALLEL:
        if n > m["vllm"].get("max_seqs", 8):
            continue
        bodies = [_body(m, [{"role": "system", "content": langer_text(f"Messlauf {zeit} gleichzeitig {n} nr {k}", 1)},
                            {"role": "user", "content": LANG}], 300) for k in range(n)]
        res = _gleichzeitig(port, bodies)
        gut = [x for x in res if isinstance(x, tuple)]
        if len(gut) < n:
            r[f"par{n}_fehler"] = next(x for x in res if not isinstance(x, tuple)) or "zeit"
            log(f"modelle: messung {mid} {n} gleichzeitig fehler {r[f'par{n}_fehler']}")
            continue
        r[f"par{n}_tok_s"] = round(sorted(x[2] for x in gut)[(n - 1) // 2], 1)     # per answer, the lower middle
        r[f"par{n}_summe"] = round(sum(x[2] for x in gut), 1)
        r[f"par{n}_erste_s"] = round(max(x[0] for x in gut), 2)
        log(f"modelle: messung {mid} {n} gleichzeitig je antwort {r[f'par{n}_tok_s']} tok/s, zusammen "
            f"{r[f'par{n}_summe']} tok/s, erste spaetestens {r[f'par{n}_erste_s']} s")
    ziel = min(LANG_ZIEL, m["kontext"] - 2048)
    kopien = max(1, ziel // _je_vorlauf(m, port))
    usage = {}
    try:
        a, _, t = stream_messen(port, _body(m, [{"role": "system", "content": langer_text(f"Messlauf {zeit} lang", kopien)},
                                                {"role": "user", "content": LANG}], 300), 900, usage=usage)
        r.update(lang_tokens=usage.get("prompt_tokens", 0), lang_erste_s=a, lang_tok_s=t)
        log(f"modelle: messung {mid} lang {r['lang_tokens']} tokens, erste {a} s, {t} tok/s")
    except Exception as e:
        r["lang_fehler"] = str(e) if isinstance(e, Fehler) else type(e).__name__.lower()[:24]
        log(f"modelle: messung {mid} lang fehler {r['lang_fehler']}")
    return r


def werkzeug_ok(antwort):
    """True when the answer calls the tool wetter for Hamburg (fixed check, nothing of the answer is kept)."""
    calls = ((antwort.get("choices") or [{}])[0].get("message") or {}).get("tool_calls") or []
    if not calls or calls[0].get("function", {}).get("name") != "wetter":
        return False
    try:
        args = json.loads(calls[0]["function"].get("arguments") or "{}")
    except ValueError:
        return False
    return "hamburg" in str(args.get("ort", "")).lower()


def _text(antwort):
    return str(((antwort.get("choices") or [{}])[0].get("message") or {}).get("content") or "")


def bild_text_ok(text):
    t = text.replace(" ", "")
    return "4711" in t and ("23,50" in t or "23.50" in t)


def bild_szene_ok(text):
    t = text.lower()
    return "rot" in t and "blau" in t and "kreis" in t and ("quadrat" in t or "viereck" in t or "rechteck" in t)


def testbilder():
    """The two fixed test pictures as PNG data URLs: printed text (a bill) and a scene (red circle, blue square)."""
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.load_default(size=44)
    a = Image.new("RGB", (900, 360), "white")
    d = ImageDraw.Draw(a)
    for i, line in enumerate(BILD_TEXT):
        d.text((50, 50 + i * 95), line, fill="black", font=font)
    b = Image.new("RGB", (640, 400), (235, 235, 235))
    d = ImageDraw.Draw(b)
    d.ellipse((60, 90, 280, 310), fill=(220, 20, 20))
    d.rectangle((370, 100, 570, 300), fill=(20, 50, 220))
    out = []
    for img in (a, b):
        buf = io.BytesIO()
        img.save(buf, "PNG")
        out.append("data:image/png;base64," + base64.b64encode(buf.getvalue()).decode())
    return out


def _bild_frage(m, url, frage):
    return _body(m, [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": url}},
                                                    {"type": "text", "text": frage}]}], 120)


ABLAGEN = ("nvme", "usb", "andere", "unbekannt")


def ablage(ordner, sys_dev="/sys/dev/block"):
    """Where the model files lie, as a fixed word of ABLAGEN: the device under the folder from /sys (no command, no
    path in the result). The engine reads the b12x table from disk on every token: on a USB disk qwen38 measured
    15.7 instead of 23.4 tok/s (2026-10-21), so the measurement says where it read from."""
    try:
        p = os.path.realpath(ordner)
        while not os.path.exists(p) and p != os.path.dirname(p):
            p = os.path.dirname(p)
        dev = os.stat(p).st_dev
        geraet = os.path.realpath(os.path.join(sys_dev, f"{os.major(dev)}:{os.minor(dev)}"))
        if not os.path.isdir(geraet):
            return "unbekannt"
        if os.path.exists(os.path.join(geraet, "partition")):
            geraet = os.path.dirname(geraet)
        if "/usb" in geraet:
            return "usb"
        if os.path.basename(geraet).startswith("nvme"):
            return "nvme"
        with open(os.path.join(geraet, "removable")) as f:
            return "usb" if f.read().strip() == "1" else "andere"
    except (OSError, ValueError):
        return "unbekannt"


class Speicher(threading.Thread):
    """Samples MemAvailable every half second; tiefst = the lowest value seen."""
    def __init__(self):
        super().__init__(daemon=True)
        self.tiefst = mem_available_gib()
        self.halt = threading.Event()

    def run(self):
        while not self.halt.wait(0.5):
            self.tiefst = min(self.tiefst, mem_available_gib())


def im_gang(text):
    """True when a line of `systemctl is-active <units>` is one of IM_GANG (any of the units works)."""
    return any(x.strip() in IM_GANG for x in str(text).splitlines())


def stand(text):
    """The last STAND_MAX progress lines of a measurement from journal text (-o cat): only lines of the fixed shape."""
    return [x for x in (y.strip() for y in str(text).splitlines()) if STAND.match(x)][-STAND_MAX:]


def _aktiv(einheit):
    if not einheit:
        return True
    return im_gang(subprocess.run(["systemctl", "is-active", einheit], capture_output=True, text=True).stdout)


def warte_bereit(m, port, einheit="", frist=GESUND_S, now=time.monotonic, sleep=time.sleep):
    """Seconds until the engine answers a real one-token request (a canary, not only /health); Fehler when the
    unit stopped or the time ran out."""
    t0 = now()
    while now() - t0 < frist:
        if not _aktiv(einheit):
            raise Fehler("engine_aus")
        try:
            _post(port, CHAT, _body(m, [{"role": "user", "content": "Hallo"}], 1), timeout=30)
            return round(now() - t0)
        except Exception:
            sleep(5)
    raise Fehler("zeit")


def bild_platz(cfg, frei_gib, kat=None):
    """Whether a picture painted during the measurement still leaves the reserve free: the picture model's need plus
    memory.reserve_gib must fit in what is available now. A fixed rule from numbers."""
    m = zur_variante("bild", cfg.get("image", {}).get("variant"), kat) or zur_variante("bild", "4b-q8", kat)
    return frei_gib >= m["need_gib"] + float(cfg.get("memory", {}).get("reserve_gib", 10))


def _bild_malen(cfg, ergebnis):
    """Paints one picture with the picture service while the language model writes (does both fit?)."""
    img = cfg.get("image", {})
    key = cfg.get("api", {}).get("key", "")
    req = urllib.request.Request(f"http://127.0.0.1:{int(img.get('port', 31005))}/v1/bild",
                                 json.dumps({"prompt": BILD_MALEN, "width": 512, "height": 512}).encode(),
                                 {"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            json.loads(r.read())
        ergebnis.update(bild_ok=True, bild_s=round(time.monotonic() - t0, 1))
    except Exception as e:
        ergebnis.update(bild_ok=False, bild_fehler=getattr(e, "code", None) or "kein_bild")


def messen_lauf(m, port=MESS_PORT, einheit="", log=print):
    """Measures one running engine; returns the result dict (numbers and fixed words only)."""
    mid = m["id"]
    speicher = Speicher()
    frei_start = speicher.tiefst
    speicher.start()
    r = {"art": m["art"], "repo": m["repo"], "gpu_gib": m["gpu_gib"], "kontext": m["kontext"], "zeit": int(time.time()),
         "profil": hardware.profil()["id"],
         "frei_start_gib": round(frei_start, 1), "ablage": ablage(hf_ordner(m))}
    log(f"modelle: messung {mid} ablage {r['ablage']}")
    try:
        r["laden_s"] = warte_bereit(m, port, einheit, laden_frist(m))
        r["frei_geladen_gib"] = round(mem_available_gib(), 1)
        r["belegt_gib"] = round(frei_start - r["frei_geladen_gib"], 1)
        log(f"modelle: messung {mid} bereit nach {r['laden_s']} s, belegt {r['belegt_gib']} GiB")
        try:
            vorher = spec_zaehler(_get(port, "/metrics"))
        except Exception:
            vorher = (0.0, 0.0)
        _post(port, CHAT, _body(m, [{"role": "user", "content": FRAGEN[0]}], 64))   # warm up
        tps, ttft = [], []
        for i, frage in enumerate(FRAGEN, 1):
            a, n, t = stream_messen(port, _body(m, [{"role": "user", "content": frage}], 400))
            ttft.append(a)
            tps.append(t)
            log(f"modelle: messung {mid} frage {i} erste {a} s, {n} tokens, {t} tok/s")
        r["erste_s"] = round(sorted(ttft)[len(ttft) // 2], 2)
        r["tok_s"] = round(sorted(tps)[len(tps) // 2], 1)
        try:
            nach = spec_zaehler(_get(port, "/metrics"))
            if nach[1] > vorher[1]:
                r["mtp_annahme"] = round((nach[0] - vorher[0]) / (nach[1] - vorher[1]), 2)
                log(f"modelle: messung {mid} mtp annahme {int(r['mtp_annahme'] * 100)} %")
        except Exception:
            pass
        if m["kontext"] >= 16384:
            r.update(cache_messen(m, port, r["zeit"], log))
        if m["art"] == "llm" and m["kontext"] >= 32768:     # a main model candidate: several at once, long context
            r.update(parallel_messen(m, port, r["zeit"], log))
        if m["werkzeuge"]:
            ok = werkzeug_ok(_post(port, CHAT, _body(
                m, [{"role": "user", "content": WERKZEUG_FRAGE}], 200, tools=[WERKZEUG], tool_choice="auto")))
            r["werkzeug"] = ok
            log(f"modelle: messung {mid} werkzeug {'ok' if ok else 'falsch'}")
        if m["kann_sehen"]:
            text_url, szene_url = testbilder()
            r["bild_text"] = bild_text_ok(_text(_post(port, CHAT, _bild_frage(m, text_url, BILD_TEXT_FRAGE))))
            r["bild_szene"] = bild_szene_ok(_text(_post(port, CHAT, _bild_frage(m, szene_url, BILD_SZENE_FRAGE))))
            log(f"modelle: messung {mid} sehen text {'ok' if r['bild_text'] else 'falsch'}, "
                f"szene {'ok' if r['bild_szene'] else 'falsch'}")
        cfg = load_config()
        # a picture painted meanwhile: for every candidate main model, also one filed to see that takes tools (Gemma 4)
        if (m["art"] == "llm" or m["werkzeuge"]) and cfg.get("image", {}).get("enabled") and not bild_platz(cfg, mem_available_gib()):
            # tars 2026-10-18: Flash Next left 8 GiB, the picture took it down to 0.1 GiB; never paint into the reserve
            log(f"modelle: messung {mid} bild gleichzeitig uebersprungen, frei {round(mem_available_gib(), 1)} GiB")
        elif (m["art"] == "llm" or m["werkzeuge"]) and cfg.get("image", {}).get("enabled"):
            maler = threading.Thread(target=_bild_malen, args=(cfg, r), daemon=True)
            maler.start()
            a, n, t = stream_messen(port, _body(m, [{"role": "user", "content": LANG}], 600))
            r["tok_s_mit_bild"] = t
            maler.join(600)
            log(f"modelle: messung {mid} bild gleichzeitig {'ok' if r.get('bild_ok') else 'fehler'}, {t} tok/s")
        r["ok"] = True
    except Exception as e:
        r["ok"] = False
        r["grund"] = str(e) if isinstance(e, Fehler) else type(e).__name__.lower()[:24]
    finally:
        speicher.halt.set()
        speicher.join(2)
        r["frei_tiefst_gib"] = round(speicher.tiefst, 1)
    log(f"modelle: messung {mid} {'fertig' if r['ok'] else 'abgebrochen ' + r['grund']}, "
        f"tiefster stand frei {r['frei_tiefst_gib']} GiB")
    return r


def merke(mid, r, path=MESSUNG):
    data = read_json(path, {})
    data.setdefault("modelle", {})[mid] = r
    data["zeit"] = r.get("zeit", int(time.time()))
    write_json(path, data, indent=1)


def zeile(mid, r):
    """One fixed line per measured model for the summary."""
    if not r.get("ok"):
        return f"modelle: ergebnis {mid} abgebrochen {r.get('grund', '?')}"
    teile = [f"{r.get('tok_s')} tok/s", f"erste {r.get('erste_s')} s", f"belegt {r.get('belegt_gib')} GiB",
             f"laden {r.get('laden_s')} s"]
    if r.get("ablage") in ABLAGEN:
        teile.append(f"ablage {r['ablage']}")
    if "frei_geladen_gib" in r:
        teile.append(f"frei geladen {r['frei_geladen_gib']} GiB")
    if "mtp_annahme" in r:
        teile.append(f"mtp {int(r['mtp_annahme'] * 100)} %")
    if "erste_warm_s" in r:
        teile.append(f"warm {r['erste_warm_s']} s")
    if "zwischenspeicher" in r:
        teile.append(f"zwischenspeicher {int(r['zwischenspeicher'] * 100)} %")
    if "mtp" in r:
        teile.append("mtp " + r["mtp"])
    for n in PARALLEL:
        if f"par{n}_tok_s" in r:
            teile.append(f"{n} gleichzeitig {r[f'par{n}_tok_s']} tok/s je antwort")
        elif f"par{n}_fehler" in r:
            teile.append(f"{n} gleichzeitig fehler {r[f'par{n}_fehler']}")
    if "lang_tokens" in r:
        teile.append(f"lang {r['lang_tokens']} tokens erste {r['lang_erste_s']} s")
    elif "lang_fehler" in r:
        teile.append(f"lang fehler {r['lang_fehler']}")
    if "platz_64k" in r:
        teile.append(f"platz {r['platz_64k']} mal 64k")
    for key, wort in (("werkzeug", "werkzeug"), ("bild_text", "text"), ("bild_szene", "szene"), ("bild_ok", "bild")):
        if key in r:
            teile.append(f"{wort} {'ok' if r[key] else 'falsch'}")
    return f"modelle: ergebnis {mid} " + ", ".join(teile)


# ---------------------------------------------------------------- the configuration file
def _roh():
    """The configuration file as it is (without the shipped defaults merged in), for a small change."""
    from common import CONFIG_PATH
    with open(CONFIG_PATH) as f:
        return json.load(f)


def _schreib(raw):
    from common import CONFIG_PATH
    write_json(CONFIG_PATH, raw, indent=2)


def rundlauf(cfg, log=print, frist=GESUND_S, now=time.monotonic, sleep=time.sleep, stufe=lambda wort: None):
    """The check before the chat switches: through the door with the API key a German sentence, a tool call, a picture
    (when the model or the image understanding model can see) and one System One question. Returns (ok, word).
    stufe: told "probe" once the engine answers, then each part that passed (llmstart, what the page shows)."""
    c = cfg.get("llm", {})
    port, key = int(c.get("port", 31006)), str(cfg.get("api", {}).get("key") or "")
    m, engine = rolle("llm", cfg)
    t0 = now()
    # first the engine itself, then the door: right after a restart the door still says "ready" from the engine before
    # (its canary runs only every KANARIE_S quiet seconds), so asking the door alone sent the questions to nobody
    # (Dominik 2026-10-18: „rundlauf bereit nach 0 s“, then httperror)
    while True:
        try:
            _get(engine, "/health")
            if json.loads(_get(port, "/health")).get("status") == "ready":
                break
        except Exception:
            pass
        if now() - t0 > frist:
            return False, "nicht bereit"
        sleep(5)
    log(f"modelle: rundlauf bereit nach {int(now() - t0)} s")
    stufe("probe")
    try:
        satz = _text(_post(port, CHAT, {"messages": [{"role": "user", "content": FRAGEN[0]}], "max_tokens": 200}, key=key))
        if len(re.findall(r"[a-zäöüß]{3,}", satz.lower())) < 5:
            return False, "satz"
        log("modelle: rundlauf satz ok")
        stufe("satz")
        if m["werkzeuge"] and not werkzeug_ok(_post(port, CHAT, {"messages": [{"role": "user", "content": WERKZEUG_FRAGE}],
                                                                 "max_tokens": 200, "tools": [WERKZEUG], "tool_choice": "auto"},
                                                         key=key)):
            return False, "werkzeug"
        log("modelle: rundlauf werkzeug ok")
        stufe("werkzeug")
        if m["kann_sehen"] or c.get("sehen_modell"):
            text_url, _ = testbilder()
            if not bild_text_ok(_text(_post(port, CHAT, dict(_bild_frage(m, text_url, BILD_TEXT_FRAGE)), key=key))):
                return False, "bild"
            log("modelle: rundlauf bild ok")
            stufe("bild")
        so = _post(port, "/v1/systemone", {"state": "Wie wird das Wetter morgen in Hamburg?", "questions": {
            "wetter": {"type": "noul", "instructions": "Fragt der Text nach dem Wetter?"}}}, key=key, timeout=60)
        p = (so.get("answers") or {}).get("wetter", {}).get("noul")
        if not isinstance(p, (int, float)) or p < 0.5:
            return False, "systemone"
        log("modelle: rundlauf systemone ok")
        stufe("systemone")
    except Exception as e:
        return False, type(e).__name__.lower()[:24]
    return True, "ok"


# ---------------------------------------------------------------- stage E4: switching models
WECHSEL = os.path.join(STATE, "modelle-wechsel.json")   # per kind the model before the last switch, for 7 days
WUNSCH = os.path.join(STATE, "modelle-wunsch.json")     # the panel's wish for the root unit speech-spark-wechsel
WECHSEL_UNIT = MODEL_LOG_UNITS["wechsel"]
# Zustand → Modelle „Messen“ (Dominik 2026-10-17): the panel's wish for the fixed root unit MESS_WUNSCH_UNIT, which
# measures like `speech-spark modelle messen` does in its transient unit MESS_UNIT; one of the two at a time
MESS_WUNSCH = os.path.join(STATE, "modelle-messen-wunsch.json")
MESS_UNIT = "speech-spark-messen"
MESS_WUNSCH_UNIT = "speech-spark-messen-wunsch"
# a oneshot unit (speech-spark-wechsel, -messen-wunsch, -update) is "activating" for as long as it works, so
# `systemctl is-active -q` alone never saw a running measurement (Dominik 2026-10-17: „Messen“ showed nothing)
IM_GANG = ("active", "activating", "deactivating", "reloading")
STAND = re.compile(r"^modelle: [A-Za-z0-9 .,:%/()_+-]{1,160}$")   # a progress line: fixed words and numbers only
STAND_MAX = 6
ALT_TAGE = 7                     # the old model stays on disk this long and can be brought back
TAUSCH = ("llm", "sehen", "asr", "tts", "bild", "musik")          # the kinds that switch (small CPU models come with features)
INSTALL = {"asr": "--asr", "tts": "--tts", "bild": "--bild", "musik": "--musik"}   # kinds install.sh sets up (wahl = its short key)
ENTFERNBAR = ("vllm", "qwen-asr", "qwen-tts")           # models that live in the Hugging Face cache


def gesamt_gib():
    """The memory pool the engines share on this computer in GiB: the one shared memory of a DGX Spark, the GPU's own
    memory of a DGX Station (hardware.profil)."""
    return hardware.profil()["pool_gib"]


def jetzt_id(art, cfg, kat=None):
    """The catalog id of the model this configuration runs for a kind that switches, "" when none runs."""
    kat = katalog() if kat is None else kat
    c = cfg.get("llm", {})
    if art == "llm":
        return c.get("modell", "") if c.get("enabled") and c.get("modell") in kat else ""
    if art == "sehen":
        return c.get("sehen_modell", "") if c.get("sehen_modell") in kat else ""
    if art == "asr":
        a = cfg.get("asr", {})
        if not a.get("enabled"):
            return ""
        m = kat.get("parakeet-primeline") if a.get("recognizer") == "parakeet" else zum_repo(a.get("model"), kat)
    elif art == "tts":
        t = cfg.get("tts", {})
        m = zum_repo(t.get("model"), kat) if t.get("enabled") else None
    elif art == "bild":
        img = cfg.get("image", {})
        m = zur_variante("bild", img.get("variant"), kat) if img.get("enabled") else None
    elif art == "musik":
        mus = cfg.get("music", {})
        m = zur_variante("musik", mus.get("variant"), kat) if mus.get("enabled") else None
    elif art == "klein":               # the re-ranking model the setting names (on or off: it is the chosen one)
        m = zur_variante("klein", cfg.get("chat", {}).get("rerank_model") or "klein", kat)
    else:
        raise Fehler("art")
    return m["id"] if m else ""


def mit_wechsel(cfg, art, m):
    """A copy of the configuration as it would be after the switch (for the budget; llm and sehen also to write)."""
    c = json.loads(json.dumps(cfg))
    if art in ROLLEN:
        c.setdefault("llm", {})[ROLLEN[art][0]] = m["id"]
    elif art == "asr":
        a = c.setdefault("asr", {})
        a["recognizer"] = "parakeet" if m["engine"] == "onnx-cpu" else "qwen"
        if m["repo"] and m["engine"] != "onnx-cpu":
            a["model"] = m["repo"]
    elif art == "tts":
        c.setdefault("tts", {})["model"] = m["repo"]
    elif art in DATEI_ART:      # a catalog variant by its choice, an own one by its own variant name
        c.setdefault("image" if art == "bild" else "music", {})["variant"] = m.get("wahl") or m["variante"]
    return c


def wechsel_pruefen(art, mid, cfg, total_gib, kat=None, messung=None, profil=None):
    """The fixed rules of a switch (the panel decides, never a model): a kind that switches, an entry of that kind from
    the catalog, for an own engine a pinned commit (catalog or measured), for the others an entry install.sh offers,
    the language model only while the own one is on (llm.enabled), not the one running, and the budget must not
    end up too tight. Returns the entry; raises Fehler with a fixed word."""
    kat = katalog() if kat is None else kat
    if art not in TAUSCH:
        raise Fehler("art")
    m = eintrag(mid, kat)
    if m["art"] != art:
        raise Fehler("art")
    if art in ROLLEN:
        if m["engine"] != "vllm":
            raise Fehler("engine")
        fest_revision(m, messung)
        if docker_bild(m):    # stage 1: measure first („Ausprobieren“); switching to it comes with stage 2
            messung = read_json(MESSUNG, {}) if messung is None else messung
            raise Fehler("docker" if ((messung.get("modelle") or {}).get(mid) or {}).get("ok") else "ungeprueft")
        if art == "llm" and not cfg.get("llm", {}).get("enabled"):
            raise Fehler("aus")
    elif not m.get("wahl") and not (m.get("eigen") and (art in SPRACH or art in DATEI_ART)):   # own: the probe decides
        raise Fehler("wahl")
    if m.get("eigen") and art == "sehen":      # stage E5: no round trip on demand, so an own one is measured first
        messung = read_json(MESSUNG, {}) if messung is None else messung
        if not ((messung.get("modelle") or {}).get(mid) or {}).get("ok"):
            raise Fehler("ungeprueft")
    if jetzt_id(art, cfg, kat) == mid:
        raise Fehler("schon")
    if budget(mit_wechsel(cfg, art, m), total_gib, kat, profil)["regel"] == "zu_knapp":
        raise Fehler("budget")
    return m


def wechsel_weg(art, m):
    """How root switches to m (one line for speech-spark.sh): „wahl <key>“ through install.sh, „sprache <repo> <commit>“
    for an own speech model and „datei <repo> <commit>“ for an own picture or music file (download, check, configuration,
    restart, probe), „vllm <repo> <commit>“ for an own engine."""
    if art in SPRACH and m.get("eigen"):
        return f"sprache {m['repo']} {m['revision']}"
    if art in DATEI_ART and m.get("eigen"):
        return f"datei {m['repo']} {m['revision']}"
    return f"wahl {m['wahl']}" if art in INSTALL else f"vllm {m['repo']} {fest_revision(m)}"


# Modellsätze (Dominik 2026-11-16 „1-6“ point 4, stage B2): the admin keeps the models of the kinds that switch under a
# name and later brings them back in one step; the panel then asks for one switch after the other (modellseite).
SAETZE = os.path.join(STATE, "modelle-saetze.json")
SATZ_LAUF = os.path.join(STATE, "modelle-satz-lauf.json")
SATZ_MAX = 10
SATZ_NAME = re.compile(r"^[A-Za-z0-9ÄÖÜäöüß][A-Za-z0-9ÄÖÜäöüß .,_-]{0,39}$")


def saetze(path=None):
    """The kept sets: [{name, modelle: {art: id}, zeit}], each checked (a broken one is left out)."""
    out = []
    for s in (read_json(path or SAETZE, {}).get("saetze") or [])[:SATZ_MAX]:
        if (isinstance(s, dict) and isinstance(s.get("name"), str) and SATZ_NAME.match(s["name"])
                and isinstance(s.get("modelle"), dict) and s["modelle"]
                and all(a in TAUSCH and isinstance(i, str) and ID.match(i) for a, i in s["modelle"].items())):
            out.append(s)
    return out


def satz_jetzt(cfg, kat=None):
    """What a set keeps: per kind that switches the model running now (kinds that are off are left out)."""
    kat = katalog() if kat is None else kat
    return {a: i for a in TAUSCH if (i := jetzt_id(a, cfg, kat))}


def satz_speichern(name, inhalt, now=None, path=None):
    """Keeps a set under its name (a set of the same name is replaced). Raises Fehler: name, leer, voll."""
    name = str(name or "").strip()
    if not SATZ_NAME.match(name):
        raise Fehler("name")
    if not inhalt:
        raise Fehler("leer")
    alle = [s for s in saetze(path) if s["name"] != name]
    if len(alle) >= SATZ_MAX:
        raise Fehler("voll")
    write_json(path or SAETZE, {"saetze": alle + [{"name": name, "modelle": dict(inhalt),
                                                    "zeit": int(time.time() if now is None else now)}]}, indent=1)


def satz_loeschen(name, path=None):
    alle = saetze(path)
    if not any(s["name"] == name for s in alle):
        raise Fehler("unbekannt")
    write_json(path or SAETZE, {"saetze": [s for s in alle if s["name"] != name]}, indent=1)


def satz_offen(name, cfg, kat=None, path=None):
    """The switches a set still needs, in the order of TAUSCH: [[art, id]] of the kinds whose model differs and is in
    the catalog. Raises Fehler("unbekannt") for a set that is not kept."""
    kat = katalog() if kat is None else kat
    s = next((x for x in saetze(path) if x["name"] == name), None)
    if s is None:
        raise Fehler("unbekannt")
    return [[a, s["modelle"][a]] for a in TAUSCH if a in s["modelle"] and s["modelle"][a] in kat
            and jetzt_id(a, cfg, kat) != s["modelle"][a]]


def wechsel_merken(art, alt, neu, now=None, path=WECHSEL):
    data = read_json(path, {})
    data[art] = {"alt": alt, "neu": neu, "zeit": int(time.time() if now is None else now)}
    write_json(path, data, indent=1)


def zurueck_ziel(art, now=None, path=WECHSEL):
    """The model before the last switch of this kind, while the 7 days run."""
    now = time.time() if now is None else now
    w = read_json(path, {}).get(art) or {}
    if not w.get("alt"):
        raise Fehler("keins")
    if now - float(w.get("zeit", 0)) > ALT_TAGE * 86400:
        raise Fehler("frist")
    return w["alt"]


def alte(cfg, now=None, path=WECHSEL, kat=None, daten=None):
    """Per kind the model before the last switch: {art: {id, tage_frei}} (days left to bring it back, 0 = gone by).
    daten: the switches as the model computer reports them, instead of the file."""
    now = time.time() if now is None else now
    out = {}
    for art, w in (read_json(path, {}) if daten is None else daten).items():
        if art in TAUSCH and isinstance(w, dict) and w.get("alt") and w["alt"] != jetzt_id(art, cfg, kat):
            out[art] = {"id": w["alt"], "tage_frei": max(0, ALT_TAGE - int((now - float(w.get("zeit", 0))) // 86400))}
    return out


def entfernbar(mid, cfg, now=None, path=WECHSEL, kat=None, hf_home=None):
    """The cache folder of a catalog model that may be removed: lives in the Hugging Face cache, no kind runs it, not
    within the 7 days to bring it back. Returns the folder; raises Fehler."""
    kat = katalog() if kat is None else kat
    m = eintrag(mid, kat)
    if m["engine"] not in ENTFERNBAR or not m["repo"]:
        raise Fehler("art")
    # a variant shares its folder with its basis: none of the entries with this repository may run
    teilen = {i for i, x in kat.items() if x["repo"] == m["repo"]}
    if any(jetzt_id(a, cfg, kat) in teilen for a in TAUSCH) or any(x["id"] in teilen for x in aktiv(cfg, 0, kat)):
        raise Fehler("aktiv")
    w = read_json(path, {}).get(m["art"]) or {}
    if w.get("alt") == mid and (time.time() if now is None else now) - float(w.get("zeit", 0)) <= ALT_TAGE * 86400:
        raise Fehler("frist")
    ordner = hf_ordner(m, hf_home)
    if not os.path.isdir(ordner) or os.path.islink(ordner):
        raise Fehler("fehlt")
    return ordner


def _wunsch_ok(art, was):
    """A switch (a kind, an id or "zurueck"), „Lange Gespräche“ (art platz, one of PLATZ) or a restart with the
    entry's settings now (art neustart, llm)."""
    return ((art in TAUSCH and (was == "zurueck" or bool(ID.match(str(was))))) or (art == "platz" and was in PLATZ)
            or (art == "neustart" and was == "llm") or (art == "laden" and bool(ID.match(str(was)))))


def wunsch_schreiben(art, was, path=WUNSCH):
    """The panel's wish (switch to an id, or "zurueck"; or art platz): checked again by root before anything happens."""
    if not _wunsch_ok(art, was):
        raise Fehler("wunsch")
    write_json(path, {"art": art, "was": was, "zeit": int(time.time())}, indent=1)


def wechsel_anfragen(art, was, cfg, total_gib, starten, laeuft=False):
    """A switch asked for (an id, or "zurueck" for the model before the last switch): the fixed rules, the wish for
    root, then starten() starts WECHSEL_UNIT. Used by the panel on this computer and by the Wärter (tarswart.py) for
    a panel on another one. Returns the entry; raises Fehler (laeuft, the rule's word, start)."""
    if laeuft:
        raise Fehler("laeuft")
    m = wechsel_pruefen(art, zurueck_ziel(art) if was == "zurueck" else was, cfg, total_gib)
    wunsch_schreiben(art, was)
    if not starten():
        raise Fehler("start")
    return m


def platz_anfragen(platz, cfg, total_gib, starten, laeuft=False):
    """„Lange Gespräche“ asked for: the fixed rules, the wish for root (art platz), then starten() starts WECHSEL_UNIT,
    which restarts the language model with it. Returns the entry as it will start; raises Fehler."""
    if laeuft:
        raise Fehler("laeuft")
    m = platz_pruefen(platz, cfg, total_gib)
    wunsch_schreiben("platz", platz)
    if not starten():
        raise Fehler("start")
    return m


def wunsch_nehmen(path=WUNSCH, now=None):
    """Root takes the wish once (the file is gone afterwards); a wish older than 10 minutes counts as none."""
    data = read_json(path, {})
    try:
        os.remove(path)
    except OSError:
        pass
    now = time.time() if now is None else now
    art, was = str(data.get("art", "")), str(data.get("was", ""))
    if not _wunsch_ok(art, was) or not 0 <= now - float(data.get("zeit", 0)) <= 600:
        raise Fehler("wunsch")
    return art, was


def messen_pruefen(mid, kat=None):
    """A model the panel may have measured: an engine this installation starts itself (vLLM), from the catalog or an
    own entry. Raises Fehler (unbekannt, engine)."""
    kat = katalog() if kat is None else kat
    if not isinstance(mid, str) or not ID.match(mid) or mid not in kat:
        raise Fehler("unbekannt")
    if kat[mid]["engine"] != "vllm":
        raise Fehler("engine")
    return kat[mid]


def messen_anfragen(mid, starten, laeuft=False, path=MESS_WUNSCH, kat=None):
    """„Messen“ asked for on Zustand → Modelle: the rule, the wish for root, then starten() starts MESS_WUNSCH_UNIT.
    laeuft: a measurement or a switch runs already. Returns the entry; raises Fehler (misst, unbekannt, engine, start)."""
    if laeuft:
        raise Fehler("misst")
    m = messen_pruefen(mid, kat)
    write_json(path, {"ids": [mid], "zeit": int(time.time())}, indent=1)
    if not starten():
        raise Fehler("start")
    return m


def messen_wunsch_nehmen(path=MESS_WUNSCH, now=None, kat=None):
    """Root takes the measuring wish once (the file is gone afterwards); older than 10 minutes counts as none."""
    data = read_json(path, {})
    try:
        os.remove(path)
    except OSError:
        pass
    now = time.time() if now is None else now
    ids = data.get("ids")
    if not isinstance(ids, list) or not 1 <= len(ids) <= 4 or not 0 <= now - float(data.get("zeit", 0)) <= 600:
        raise Fehler("wunsch")
    return [messen_pruefen(i, kat)["id"] for i in ids]


# ---------------------------------------------------------------- stage E5: the admin's own models
EIGENE = os.path.join(STATE, "modelle-eigene.json")     # own entries the admin added (Zustand → Modelle)
EIGENE_MAX = 20
HF_API, HF_INFO_MAX = hftoken.API, hftoken.MAX_BYTES     # the metadata of one commit, its answer at most
# architectures the engine runs without code from the repository (vLLM's own model classes); nothing else is added
VLLM_ARCH = {
    "llm": ("Qwen3ForCausalLM", "Qwen3MoeForCausalLM", "Qwen2ForCausalLM", "Qwen2MoeForCausalLM", "LlamaForCausalLM",
            "MistralForCausalLM", "MixtralForCausalLM", "Gemma2ForCausalLM", "Gemma3ForCausalLM", "Phi3ForCausalLM",
            "GraniteForCausalLM", "OlmoForCausalLM", "Olmo2ForCausalLM", "GptOssForCausalLM"),
    "sehen": ("Qwen2VLForConditionalGeneration", "Qwen2_5_VLForConditionalGeneration", "Qwen3VLForConditionalGeneration",
              "Qwen3VLMoeForConditionalGeneration", "Gemma3ForConditionalGeneration", "Mistral3ForConditionalGeneration",
              "LlavaForConditionalGeneration", "Idefics3ForConditionalGeneration", "InternVLChatModel"),
}
# the engine's parsers per family (fixed; a family without one gets no tools, the round trip then decides)
PARSER_FAMILIE = {"Qwen3": {"reasoning_parser": "qwen3", "tool_call_parser": "hermes"},
                  "Qwen2": {"tool_call_parser": "hermes"}, "Llama": {"tool_call_parser": "llama3_json"},
                  "Mistral": {"tool_call_parser": "mistral"}, "Mixtral": {"tool_call_parser": "mistral"}}
FREI = ("apache-2.0", "mit", "bsd-2-clause", "bsd-3-clause", "openrail", "cc-by-4.0", "llama3.1", "llama3.2", "llama3.3",
        "gemma", "qwen")                # licences that allow commercial use (others are shown as "nur privat")
KV_GIB = {"llm": 12, "sehen": 4}      # room for the context beside the weights (32K tokens)
# own speech models (Dominik 2026-11-16 „alle 1-6“, slot „Hören“ and „Sprechen“): the program that runs the kind, its
# checked catalog models the family is taken from, and the room an own one needs beside its weights. An own one must
# be the same family (FAMILIE_KEYS of its config.json equal to the reference's) as a checked model of that program,
# so the program can load it without code of its own; it is used only after the fixed probe (sprachprobe.py).
SPRACH = {"asr": ("qwen-asr", ("qwen3-asr-1.7b", "qwen3-asr-0.6b")),
          "tts": ("qwen-tts", ("qwen3-tts-1.7b", "qwen3-tts-0.6b"))}
SPRACH_EXTRA_GIB = 3
FAMILIE_KEYS = ("architectures", "model_type", "tts_model_type")
EXTRA_GIB = dict(KV_GIB, **{a: SPRACH_EXTRA_GIB for a in SPRACH})


# own picture and music models (slot „Bilder“ and „Musik“): one GGUF file in place of the main model of a basis variant
# (bildmodell.VARIANTS / musikmodell.VARIANTS), everything else of the basis; its header must name the same family
# as the basis's file (bildmodell.gguf_arch), checked on the model computer before the switch, then the fixed probe
DATEI_ART = {"bild": ("sdcpp", ("4b-q8", "9b-q8"), "model"), "musik": ("acestepcpp", ("2b", "xl"), "dit")}
DATEI_PFAD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}\.gguf$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def basis_variante(art, basis):
    import bildmodell
    import musikmodell
    return (bildmodell.VARIANTS if art == "bild" else musikmodell.VARIANTS).get(basis)


def datei_ok(d):
    """The own file of a picture or music entry: a .gguf path inside the repository, its SHA-256 and size."""
    return (isinstance(d, dict) and set(d) == {"path", "sha256", "size"} and isinstance(d["path"], str)
            and DATEI_PFAD.match(d["path"]) is not None and ".." not in d["path"] and isinstance(d["sha256"], str)
            and SHA256.match(d["sha256"]) is not None and isinstance(d["size"], int) and not isinstance(d["size"], bool)
            and 0 < d["size"] < 400 * 10**9)


def datei_vorschlag(info, art, repo, datei, basis, total_gib, mit_token=False):
    """An own picture or music entry from the Hugging Face metadata of one commit: the named .gguf file of it (size
    and SHA-256 from its LFS pointer) in place of the basis variant's main model. Raises Fehler with a fixed word."""
    if art not in DATEI_ART:
        raise Fehler("art")
    if not REPO.match(str(repo)) or ".." in repo:
        raise Fehler("repo")
    if basis not in DATEI_ART[art][1]:
        raise Fehler("basis")
    if not isinstance(info, dict) or not REV.match(str(info.get("sha", ""))):
        raise Fehler("antwort")
    _zugang(info, mit_token)
    x = next((x for x in info.get("siblings") or [] if isinstance(x, dict) and x.get("rfilename") == datei), None)
    lfs = x.get("lfs") if isinstance(x, dict) and isinstance(x.get("lfs"), dict) else {}
    d = {"path": str(datei), "sha256": lfs.get("sha256"), "size": lfs.get("size")}
    if not datei_ok(d) or not _name_frei(art, datei):
        raise Fehler("format")
    b = basis_variante(art, basis)
    alt = b[DATEI_ART[art][2]].size
    need = max(1, round(b["need_gib"] + (d["size"] - alt) / 2**30))
    if need / total_gib > ANTEIL_MAX:
        raise Fehler("budget")
    card = info.get("cardData") if isinstance(info.get("cardData"), dict) else {}
    lizenz = _wort(card.get("license") if isinstance(card.get("license"), str) else "", 32) or "unbekannt"
    stamm = os.path.basename(datei)[:-5]
    name = re.sub(r"[^A-Za-z0-9 ._-]+", "", stamm)[:48] or "Modell"
    mid = ("eigen-" + _wort(stamm, 41)).rstrip("-.")
    return eigen_ok({"id": mid, "art": art, "name": {"de": name, "en": name}, "engine": DATEI_ART[art][0],
                     "variante": mid, "basis": basis, "datei": d, "repo": repo, "revision": info["sha"],
                     "lizenz": lizenz, "gewerblich": lizenz in FREI, "platte_gb": max(1, round(d["size"] / 1e9)),
                     "need_gib": need, "gemessen": False, "betrieb": "bei_bedarf", "eigen": True})


def _name_frei(art, datei):
    """An own file is kept under its own name in the kind's folder: never the name of a catalog file there."""
    import bildmodell
    import musikmodell
    mod = bildmodell if art == "bild" else musikmodell
    fest = {f.name for v in mod.VARIANTS for f in mod.files(v) if v in mod.VARIANTS}
    return os.path.basename(datei) not in fest


# Eigene kleine Modelle (Dominik 2026-11-16 „alle 1-6“ point 2 „klein via ONNX“, 2026-11-17 „mache das projekt bis zu
# ende durch“): only the re-ranking (chat.rerank_model) takes an own one; the meaning search's embedding stays, because
# every stored vector belongs to its model. It runs on the panel's computer on the CPU (nachsortieren.py,
# embed_worker.py), so its entry is kept there, also beside a model computer.
KLEIN_ROLLE = {"nachsortieren": ("rerank-klein", "rerank-gross")}   # the checked models whose families an own one must share
ONNX_PFAD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}\.onnx$")
KLEIN_MAX_BYTES = 2 * 2**30            # one ONNX file without external data (protobuf's own limit)
KLEIN_NEED_GIB = 6.0                   # like the large checked one: the worker starts only with this much free memory
KLEIN_PROBE = ("Wie hoch ist der Eiffelturm?",
               ("Der Eiffelturm in Paris ist mit Antenne etwa 330 Meter hoch.",
                "Kartoffeln werden im Frühjahr gepflanzt und im Herbst geerntet."))


def klein_ok(d):
    """The own file of a small model: an .onnx path inside the repository, its SHA-256 and size (at most 2 GiB)."""
    return (isinstance(d, dict) and set(d) == {"path", "sha256", "size"} and isinstance(d["path"], str)
            and ONNX_PFAD.match(d["path"]) is not None and ".." not in d["path"] and isinstance(d["sha256"], str)
            and SHA256.match(d["sha256"]) is not None and isinstance(d["size"], int) and not isinstance(d["size"], bool)
            and 0 < d["size"] <= KLEIN_MAX_BYTES)


def klein_vorschlag(info, repo, datei, familien=()):
    """An own re-ranking model from the Hugging Face metadata of one commit: the named .onnx file (size and SHA-256 from
    its LFS pointer, no external data beside it), a tokenizer.json, no code, open (the panel's computer has no token),
    and the family of its config.json one of familien (those of the checked re-rankers). Raises Fehler with a word."""
    if not REPO.match(str(repo)) or ".." in repo:
        raise Fehler("repo")
    if not isinstance(info, dict) or not REV.match(str(info.get("sha", ""))):
        raise Fehler("antwort")
    _zugang(info, False)
    files = {x.get("rfilename"): x for x in info.get("siblings") or [] if isinstance(x, dict) and isinstance(x.get("rfilename"), str)}
    x = files.get(datei) or {}
    lfs = x.get("lfs") if isinstance(x.get("lfs"), dict) else {}
    d = {"path": str(datei), "sha256": lfs.get("sha256"), "size": lfs.get("size")}
    if (not klein_ok(d) or "tokenizer.json" not in files or len(files) > 2000
            or any(f.startswith(datei) and f != datei for f in files)):      # model.onnx_data, model.onnx.data
        raise Fehler("format" if not (isinstance(d["size"], int) and d["size"] > KLEIN_MAX_BYTES) else "budget")
    cfg = info.get("config") if isinstance(info.get("config"), dict) else {}
    if any(w in json.dumps(cfg) for w in ('"auto_map"', "trust_remote_code")):
        raise Fehler("code")
    if familie(cfg) is None or familie(cfg) not in familien:
        raise Fehler("familie")
    card = info.get("cardData") if isinstance(info.get("cardData"), dict) else {}
    lizenz = _wort(card.get("license") if isinstance(card.get("license"), str) else "", 32) or "unbekannt"
    name = re.sub(r"[^A-Za-z0-9 ._-]+", "", repo.split("/", 1)[1])[:48] or "Modell"
    mid = ("eigen-" + _wort(repo.split("/", 1)[1] + "-" + os.path.basename(datei)[:-5], 41)).rstrip("-.")
    return eigen_ok({"id": mid, "art": "klein", "rolle": "nachsortieren", "variante": mid, "name": {"de": name, "en": name},
                     "engine": "onnx-cpu", "datei": d, "repo": repo, "revision": info["sha"], "lizenz": lizenz,
                     "gewerblich": lizenz in FREI, "platte_gb": max(0.01, round(d["size"] / 1e9, 2)),
                     "need_gib": KLEIN_NEED_GIB, "gemessen": False, "betrieb": "bei_bedarf", "eigen": True})


def klein_pruefen(mid, cfg, kat=None):
    """The fixed rules for using a re-ranking model (a checked one or an own one): an entry of that role, not the one
    set now. Returns the entry; raises Fehler with a fixed word. The probe at its first start decides (nachsortieren)."""
    kat = katalog() if kat is None else kat
    m = kat.get(mid)
    if not m or m["art"] != "klein" or m.get("rolle") != "nachsortieren" or not m.get("variante"):
        raise Fehler("art")
    if jetzt_id("klein", cfg, kat) == mid:
        raise Fehler("schon")
    return m


def klein_probe(scores):
    """The fixed probe of a re-ranking model: the passage that answers KLEIN_PROBE's question must score higher than the
    one that does not. (ok, word)."""
    if not (isinstance(scores, list) and len(scores) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in scores)):
        return False, "antwort"
    return (True, "ok") if scores[0] > scores[1] else (False, "reihenfolge")


def datei_laden(mid, kat=None, log=print):
    """Root's step before the switch to an own picture or music file (as the panel's user): fetch the variant's files
    (bildmodell.fetch: size and SHA-256), then the own file's GGUF header must name the same family as its basis's
    main file on the disk. Raises Fehler with a fixed word."""
    import bildmodell
    import musikmodell
    m = eintrag(mid, kat)
    if not m.get("eigen") or m["art"] not in DATEI_ART:
        raise Fehler("art")
    mod = bildmodell if m["art"] == "bild" else musikmodell
    if not _name_frei(m["art"], m["datei"]["path"]):
        raise Fehler("format")
    key = DATEI_ART[m["art"]][2]
    basis_datei = bildmodell.path(mod.VARIANTS[m["basis"]][key], mod.FOLDER)
    if bildmodell.file_size(basis_datei) != mod.VARIANTS[m["basis"]][key].size:
        raise Fehler("basis")
    if not bildmodell.fetch(mod.files(mid), mod.FOLDER, token=hftoken.token() or None):
        raise Fehler("nicht_geladen")
    a, b = bildmodell.gguf_arch(bildmodell.path(mod.alle()[mid][key], mod.FOLDER)), bildmodell.gguf_arch(basis_datei)
    if not a or a != b:
        raise Fehler("familie")
    log(f"modelle: datei {m['art']} ok")


DATEI_PROBE_BILD = "Ein roter Apfel auf einem Holztisch, Tageslicht"
DATEI_PROBE_MUSIK = "ruhige Klaviermusik, langsam"
DATEI_PROBE_MIN_STD = 8.0          # a picture whose pixels hardly differ (one colour, noise-free grey) is no picture
DATEI_PROBE_MIN_MP3 = 40_000       # ten seconds of MP3 are well above this; an empty or broken answer is not


def datei_probe(art, cfg=None, post=None):
    """The fixed probe after the switch to an own picture or music file: paint one fixed picture (its pixels must
    differ, DATEI_PROBE_MIN_STD) or make ten seconds of fixed music (at least DATEI_PROBE_MIN_MP3 bytes). (ok, word)."""
    import base64
    import io
    cfg = load_config() if cfg is None else cfg
    post = post or _post
    key = cfg.get("api", {}).get("key", "")
    try:
        if art == "bild":
            r = post(int(cfg.get("image", {}).get("port", 31005)), "/v1/bild",
                     {"prompt": DATEI_PROBE_BILD, "width": 512, "height": 512, "seed": 7}, 900, key)
            from PIL import Image, ImageStat
            with Image.open(io.BytesIO(base64.b64decode(r["png"]))) as im:
                std = max(ImageStat.Stat(im.convert("RGB")).stddev)
            return (std >= DATEI_PROBE_MIN_STD), ("ok" if std >= DATEI_PROBE_MIN_STD else "leer")
        if art == "musik":
            r = post(int(cfg.get("music", {}).get("port", 31004)), "/v1/musik",
                     {"caption": DATEI_PROBE_MUSIK, "seconds": 10, "seed": 7}, 1800, key)
            n = len(base64.b64decode(r["mp3"]))
            return (n >= DATEI_PROBE_MIN_MP3), ("ok" if n >= DATEI_PROBE_MIN_MP3 else "leer")
    except Exception:
        return False, "antwort"
    raise Fehler("art")


def sprach_eigen(sec, repo, kat=None):
    """True when repo is an own speech model (SPRACH) of this kind in the catalog: the configuration may then name it
    beside Qwen's own (common.MODEL_ID); engine.sh checks the same before it starts (modelle.py sprach-eigen)."""
    m = zum_repo(repo, kat) if sec in SPRACH and isinstance(repo, str) and REPO.match(repo) and ".." not in repo else None
    return bool(m and m.get("eigen") and m["art"] == sec and m["engine"] == SPRACH[sec][0])


def eigene_eintraege(art, path=None):
    """The own entries of one kind that pass eigen_ok (bildmodell.eigene builds the own variants from them)."""
    out = []
    for m in eigene(path or EIGENE):
        try:
            eigen_ok(m)
        except Fehler:
            continue
        if m["art"] == art:
            out.append(m)
    return out


def familie(cfg):
    """The family of a model from its config.json as Hugging Face gives it: (architectures, model_type, …) or None."""
    if not isinstance(cfg, dict):
        return None
    f = tuple(json.dumps(cfg.get(k), sort_keys=True) if cfg.get(k) is not None else "" for k in FAMILIE_KEYS)
    return f if any(f) else None
EIGEN_KONTEXT = 32768


def eigen_ok(m):
    """The extra rules for an own entry: an own id, an engine of this installation on a pinned commit, only measured
    on request; a speech model only for its kind's program (SPRACH), never a picture or music model yet."""
    pruefe_eintrag(m)
    if m.get("art") in DATEI_ART:     # an own picture or music file in place of its basis's main model
        e, basen, _ = DATEI_ART[m["art"]]
        if not (m.get("eigen") is True and str(m["id"]).startswith("eigen-") and m["engine"] == e
                and m.get("variante") == m["id"] and m.get("basis") in basen and datei_ok(m.get("datei"))
                and REV.match(m["revision"]) and not {"vllm", "wahl", "rolle", "empfohlen"} & set(m)):
            raise Fehler("eigen")
        return m
    if m.get("art") == "klein":       # an own re-ranking model: one ONNX file on the panel's computer
        if not (m.get("eigen") is True and str(m["id"]).startswith("eigen-") and m["engine"] == "onnx-cpu"
                and m.get("rolle") in KLEIN_ROLLE and m.get("variante") == m["id"] and klein_ok(m.get("datei"))
                and REV.match(m["revision"]) and not {"vllm", "wahl", "empfohlen", "basis"} & set(m)):
            raise Fehler("eigen")
        return m
    if m.get("art") in SPRACH:        # an own speech model: its kind's program, a pinned commit, never a choice of install.sh
        if not (m.get("eigen") is True and str(m["id"]).startswith("eigen-") and m["engine"] == SPRACH[m["art"]][0]
                and REV.match(m["revision"]) and not {"vllm", "wahl", "rolle", "empfohlen", "variante"} & set(m)):
            raise Fehler("eigen")
        return m
    if not (m.get("eigen") is True and str(m["id"]).startswith("eigen-") and m["engine"] == "vllm"
            and m["art"] in VLLM_ARCH and REV.match(m["revision"]) and m.get("messen") == "auf_wunsch"
            and m.get("vllm", {}).get("venv", "llm") == "llm" and not {"quantization", "docker"} & set(m.get("vllm", {}))
            and "empfohlen" not in m):        # only a checked catalog entry is recommended
        raise Fehler("eigen")
    return m


def _wort(text, n=40):
    return re.sub(r"[^a-z0-9.-]+", "-", str(text or "").lower()).strip("-.")[:n]


def _zugang(info, mit_token):
    """Private or switched off: never. A model that needs an approval (gated) only with the admin's token on the model
    computer (Dominik 2026-11-16 „ja“); whether the admin accepted its terms Hugging Face decides at the download."""
    if info.get("private") or info.get("disabled") or (info.get("gated") and not mit_token):
        raise Fehler("zugang")


def eigen_vorschlag(info, art, repo, total_gib, mit_token=False, familien=()):
    """An own catalog entry from the Hugging Face metadata of one commit (the panel reads it, the model never):
    weights only as safetensors, no code from the repository, an architecture the engine knows, it must fit within
    ANTEIL_MAX. A speech model (SPRACH) instead must be of one of familien (those of its program's checked models).
    Returns the entry; raises Fehler with a fixed word."""
    if art not in VLLM_ARCH and art not in SPRACH:
        raise Fehler("art")
    if not REPO.match(str(repo)) or ".." in repo:
        raise Fehler("repo")
    if not isinstance(info, dict) or not REV.match(str(info.get("sha", ""))):
        raise Fehler("antwort")
    _zugang(info, mit_token)
    files = [x for x in info.get("siblings") or [] if isinstance(x, dict) and isinstance(x.get("rfilename"), str)]
    weights = [x for x in files if x["rfilename"].endswith(".safetensors")]
    if not weights or len(files) > 2000:
        raise Fehler("format")
    cfg = info.get("config") if isinstance(info.get("config"), dict) else {}
    if any(w in json.dumps(cfg) for w in ('"auto_map"', "trust_remote_code")):     # also a tokenizer's own code
        raise Fehler("code")
    arch = (cfg.get("architectures") or [""])[0]
    if art in SPRACH:
        if familie(cfg) is None or familie(cfg) not in familien:
            raise Fehler("familie")
    elif arch not in VLLM_ARCH[art] and not (art == "llm" and arch in VLLM_ARCH["sehen"]):
        raise Fehler("architektur")

    def size(x):
        lfs = x.get("lfs") if isinstance(x.get("lfs"), dict) else {}
        v = lfs.get("size", x.get("size"))
        return v if isinstance(v, int) and v >= 0 else None
    sizes = [size(x) for x in weights]
    if None in sizes:
        raise Fehler("format")
    gib = sum(sizes) / 2**30
    need = gib + EXTRA_GIB[art]
    if need / total_gib > ANTEIL_MAX:
        raise Fehler("budget")
    card = info.get("cardData") if isinstance(info.get("cardData"), dict) else {}
    lizenz = _wort(card.get("license") if isinstance(card.get("license"), str) else "", 32) or "unbekannt"
    name = re.sub(r"[^A-Za-z0-9 ._-]+", "", repo.split("/", 1)[1])[:48] or "Modell"
    if art in SPRACH:
        return eigen_ok({"id": ("eigen-" + _wort(repo.split("/", 1)[1], 41)).rstrip("-."), "art": art,
                         "name": {"de": name, "en": name}, "engine": SPRACH[art][0], "repo": repo, "revision": info["sha"],
                         "lizenz": lizenz, "gewerblich": lizenz in FREI, "platte_gb": max(1, round(sum(sizes) / 1e9)),
                         "need_gib": max(1, round(need)), "gemessen": False, "betrieb": "resident", "eigen": True})
    sehen = arch in VLLM_ARCH["sehen"]
    fam = next((v for k, v in PARSER_FAMILIE.items() if arch.startswith(k)), {})
    m = {"id": ("eigen-" + _wort(repo.split("/", 1)[1], 41)).rstrip("-."), "art": art, "name": {"de": name, "en": name},
         "engine": "vllm", "repo": repo, "revision": info["sha"], "lizenz": lizenz, "gewerblich": lizenz in FREI,
         "platte_gb": max(1, round(sum(sizes) / 1e9)), "need_gib": max(1, round(need)), "gemessen": False,
         "gpu_gib": round(need + 0.01 * total_gib, 1), "kontext": EIGEN_KONTEXT,
         "kann_sehen": sehen, "werkzeuge": art == "llm" and "tool_call_parser" in fam,
         "vllm": dict(fam if art == "llm" else {}, max_seqs=4), "anfrage": {}, "messen": "auf_wunsch",
         "betrieb": "resident" if art == "llm" else "bei_bedarf", "eigen": True}
    return eigen_ok(m)



# Zustand → Modelle „Suchen“ (Dominik 2026-10-17 „3a“): Hugging Face's public search for the language model or image
# understanding. The hits are data: each one only gets the quick rules below (the full check of eigen_vorschlag runs
# again on „Hinzufügen“, on the pinned commit), nothing is downloaded or added by searching.
HF_SUCHE = ("https://huggingface.co/api/models?search={q}&filter=safetensors&sort=downloads&direction=-1&limit=40"
            "&expand[]=config&expand[]=tags&expand[]=safetensors&expand[]=downloads&expand[]=cardData&expand[]=gated"
            "&expand[]=pipeline_tag")
SUCHE_Q = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/-]{1,59}$")
SUCHE_MAX = 20
SUCHE_ANTWORT_MAX = 4 * 1024 * 1024
# bytes per weight of a dtype in the safetensors header (packed 4-bit formats come as U8 or I8)
DTYPE_BYTES = {"F64": 8, "I64": 8, "F32": 4, "I32": 4, "U32": 4, "BF16": 2, "F16": 2, "I16": 2, "U16": 2,
               "F8_E4M3": 1, "F8_E5M2": 1, "F8_E8M0": 1, "I8": 1, "U8": 1, "BOOL": 1}


# „Empfehlung“ in the search (Dominik 2026-11-16 „wie wäre es noch mit einer empfehlung welches model gut passen würde?
# je nach anwendung“, „1-3“): fixed rules, never a model's judgement. The task Hugging Face names (pipeline_tag) must
# fit the kind (an embedding or a voice is no language model); the hits that fit come first, by the format the
# computer runs best (FORMAT_RANG), then by downloads; the first of them that also fits beside the running models
# gets the star, with its reasons (format, memory).
SUCHE_AUFGABEN = {"llm": ("text-generation", "image-text-to-text"), "sehen": ("image-text-to-text",),
                  "asr": ("automatic-speech-recognition",), "tts": ("text-to-speech", "text-to-audio")}
FORMATE = ("nvfp4", "fp8", "int", "bf16")
FORMAT_RANG = {True: {"nvfp4": 3, "fp8": 2, "int": 1, "bf16": 1},      # a GPU that runs NVFP4 (hardware.FP4)
               False: {"fp8": 3, "int": 2, "bf16": 2, "nvfp4": 0}}


def format_wort(repo, par=None):
    """The weights' format from the name and the dtypes of the safetensors header: nvfp4, fp8, int or bf16."""
    n = str(repo).lower()
    par = par or {}
    f8 = sum(v for k, v in par.items() if k.startswith("F8_") and isinstance(v, int))
    alle = sum(v for v in par.values() if isinstance(v, int)) or 1
    if "fp4" in n:
        return "nvfp4"
    if "fp8" in n or f8 * 2 > alle:
        return "fp8"
    if any(w in n for w in ("awq", "gptq", "int4", "int8", "w4a16", "w8a8", "bnb")):
        return "int"
    return "bf16"


def empfohlen(art, kat, profil):
    """The checked catalog model this kind of computer should take for art (modelle.json "empfohlen"), else ""."""
    k = hardware.klasse(profil)
    return next((mid for mid, m in kat.items() if m["art"] == art and k in m.get("empfohlen", ())), "")


def such_url(q):
    """The search address for an admin's words (letters, digits, space and ._/- only); Fehler("suche") otherwise."""
    q = str(q or "").strip()
    if not SUCHE_Q.match(q) or ".." in q:
        raise Fehler("suche")
    return HF_SUCHE.format(q=urllib.request.quote(q, safe=""))


def such_treffer(items, art, total_gib, kat=None, profil=None, raum_gib=None, mit_token=False, familien=()):
    """The hits for the page: [{repo, downloads, lizenz, gb, need_gib, format, nein, aufgabe, empfohlen}], „nein“ a fixed
    word when a rule already says no (schon, zugang, aufgabe, code, format, architektur, budget); names that do not match
    REPO are dropped. The fitting ones first (FORMAT_RANG for this computer, then downloads), the others after them;
    „empfohlen“ for the first fitting one whose need is known and at most raum_gib (the room beside the other
    running models), with „warum“ {format, need_gib, raum_gib}. A model that needs an approval only with the token.
    A speech model (SPRACH) must be of one of familien instead of a known architecture („familie“ otherwise)."""
    if art not in VLLM_ARCH and art not in SPRACH:
        raise Fehler("art")
    if not isinstance(items, list):
        raise Fehler("antwort")
    kat = katalog() if kat is None else kat
    profil = profil or hardware.profil()
    rang = FORMAT_RANG[profil.get("id") in hardware.FP4]
    da = {m.get("repo") for m in kat.values()}
    out = []
    for x in items:
        if not isinstance(x, dict) or len(out) >= 2 * SUCHE_MAX:
            continue
        repo = x.get("id") if isinstance(x.get("id"), str) else ""
        if not REPO.match(repo) or ".." in repo:
            continue
        tags = [t for t in x.get("tags") or [] if isinstance(t, str)]
        cfg = x.get("config") if isinstance(x.get("config"), dict) else {}
        arch = (cfg.get("architectures") or [""])[0] if isinstance(cfg.get("architectures"), list) else ""
        st = x.get("safetensors") if isinstance(x.get("safetensors"), dict) else {}
        par = st.get("parameters") if isinstance(st.get("parameters"), dict) else {}
        par = {k: v for k, v in par.items() if isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool) and v >= 0}
        byte = sum(v * DTYPE_BYTES.get(k, 2) for k, v in par.items())
        gib = byte / 2**30 if byte else None
        need = round(gib + EXTRA_GIB[art]) if gib is not None else None
        card = x.get("cardData") if isinstance(x.get("cardData"), dict) else {}
        lizenz = _wort(card.get("license") if isinstance(card.get("license"), str) else "", 32) or "unbekannt"
        aufgabe = _wort(x.get("pipeline_tag") if isinstance(x.get("pipeline_tag"), str) else "", 32)
        if repo in da:
            nein = "schon"
        elif x.get("private") or x.get("disabled") or (x.get("gated") and not mit_token):
            nein = "zugang"
        elif aufgabe and aufgabe not in SUCHE_AUFGABEN[art]:
            nein = "aufgabe"
        elif "custom_code" in tags or "auto_map" in json.dumps(cfg):
            nein = "code"
        elif "safetensors" not in tags and not par:
            nein = "format"
        elif art in SPRACH and familie(cfg) not in familien:
            nein = "familie"
        elif art not in SPRACH and arch not in VLLM_ARCH[art] and not (art == "llm" and arch in VLLM_ARCH["sehen"]):
            nein = "architektur"
        elif need is not None and need / total_gib > ANTEIL_MAX:
            nein = "budget"
        else:
            nein = ""
        d = x.get("downloads")
        out.append({"repo": repo, "downloads": d if isinstance(d, int) and d >= 0 else 0, "lizenz": lizenz,
                    "gewerblich": lizenz in FREI, "gb": round(byte / 1e9, 1) if byte else None, "need_gib": need,
                    "format": format_wort(repo, par), "aufgabe": aufgabe, "nein": nein, "empfohlen": False})
    out.sort(key=lambda h: (h["nein"] != "", -rang[h["format"]] if not h["nein"] else 0, -h["downloads"]))
    out = out[:SUCHE_MAX]
    for h in out:
        if not h["nein"] and h["need_gib"] is not None and (raum_gib is None or h["need_gib"] <= raum_gib):
            h["empfohlen"] = True
            h["warum"] = {"format": h["format"], "need_gib": h["need_gib"],
                          "raum_gib": round(raum_gib if raum_gib is not None else total_gib, 1)}
            break
    return out


# „Ausprobieren“ (Dominik 2026-10-17 „2a“): „Messen“ with a note; once the measurement of that model is done the page
# asks, with the numbers, whether to switch. One note at a time, for a day; a switch or „Verwerfen“ removes it.
PROBE = os.path.join(STATE, "modelle-probe.json")
PROBE_SEK = 86400


def probe_merken(mid, art, path=PROBE, now=None):
    if not ID.match(str(mid)) or art not in TAUSCH:
        raise Fehler("wunsch")
    write_json(path, {"id": mid, "art": art, "zeit": int(time.time() if now is None else now)}, indent=1)


def probe_weg(path=PROBE):
    try:
        os.remove(path)
        return True
    except FileNotFoundError:
        return False


def probe_stand(kat, messung, laufend, misst, path=PROBE, now=None):
    """For the page: {id, art, fertig, ok, tok_s, jetzt_id, jetzt_tok_s} of the model being tried, None without one."""
    p = read_json(path, {})
    now = time.time() if now is None else now
    mid, art = str(p.get("id", "")), str(p.get("art", ""))
    try:
        zeit = float(p.get("zeit", 0))
    except (TypeError, ValueError):
        return None
    if mid not in kat or kat[mid]["art"] != art or not 0 <= now - zeit <= PROBE_SEK:
        return None
    r = (messung.get("modelle") or {}).get(mid) or {}
    fertig = not misst and isinstance(r.get("zeit"), (int, float)) and r["zeit"] >= zeit - 60
    jetzt = next((i for i in laufend if i in kat and kat[i]["art"] == art), "")
    rj = (messung.get("modelle") or {}).get(jetzt) or {}
    return {"id": mid, "art": art, "fertig": fertig, "ok": fertig and r.get("ok") is not False,
            "tok_s": r.get("tok_s") if fertig else None, "jetzt_id": jetzt, "jetzt_tok_s": rj.get("tok_s")}

# Rezept-Editor (Dominik 2026-11-16 „1-6“, model catalog stage B1): an own entry gets the engine settings a catalog
# entry has, from fixed ranges and fixed words only (never a flag of its own). The checked numbers of a recipe that
# changed are gone with it: the model is measured again. A good recipe leaves as a ready catalog line (katalog_zeile).
PARSER_NAMEN = ("qwen3", "qwen3_coder", "qwen3_xml", "hermes", "gemma4", "llama3_json", "mistral", "deepseek_r1")
REZEPT_ZAHLEN = {"kontext": (2048, 262144), "gpu_gib": (1, GPU_GIB_MAX), "max_seqs": (1, 16), "mtp": (0, 8),
                 "batched_tokens": (2048, 32768), "bilder_pro_frage": (1, 8)}
REZEPT_WOERTER = {"kv_cache_dtype": KV, "reasoning_parser": PARSER_NAMEN, "tool_call_parser": PARSER_NAMEN}
REZEPT_FELDER = tuple(REZEPT_ZAHLEN) + tuple(REZEPT_WOERTER) + ("entwurf", "entwurf_revision")
OBEN = ("kontext", "gpu_gib")          # fields of the entry itself; the others live in its "vllm"


def rezept(m):
    """The recipe of an entry for the form: every field of REZEPT_FELDER, "" or 0 where it has none."""
    v = m.get("vllm") or {}
    out = {k: (m.get(k) if k in OBEN else v.get(k)) for k in REZEPT_FELDER}
    return {k: (x if x is not None else (0 if k in REZEPT_ZAHLEN else "")) for k, x in out.items()}


def rezept_anwenden(m, felder, total_gib):
    """The own entry m with the recipe fields set (only REZEPT_FELDER; "" or 0 takes a field out). Raises Fehler with a
    fixed word: felder (unknown field or wrong kind), a field's name (out of range or unknown word), budget (does not
    fit this computer), and every rule of eigen_ok."""
    if not isinstance(m, dict) or not m.get("eigen"):
        raise Fehler("eigen")
    if not isinstance(felder, dict) or set(felder) - set(REZEPT_FELDER) or not felder:
        raise Fehler("felder")
    n = json.loads(json.dumps(m))
    v = n.setdefault("vllm", {})
    for k, x in felder.items():
        ziel = n if k in OBEN else v
        if k in REZEPT_ZAHLEN:
            lo, hi = REZEPT_ZAHLEN[k]
            if isinstance(x, bool) or not isinstance(x, (int, float)) or (k != "gpu_gib" and x != int(x)):
                raise Fehler(k)
            if x == 0 and k not in OBEN:
                ziel.pop(k, None)
                continue
            if not lo <= x <= hi:
                raise Fehler(k)
            ziel[k] = round(float(x), 1) if k == "gpu_gib" else int(x)
        elif not isinstance(x, str):
            raise Fehler(k)
        elif x == "":
            ziel.pop(k, None)
        elif k in REZEPT_WOERTER and x not in REZEPT_WOERTER[k]:
            raise Fehler(k)
        elif k == "entwurf" and (not REPO.match(x) or ".." in x):
            raise Fehler(k)
        elif k == "entwurf_revision" and not REV.match(x):
            raise Fehler(k)
        else:
            ziel[k] = x
    if "bilder_pro_frage" in v and not n["kann_sehen"]:
        raise Fehler("bilder_pro_frage")
    n["werkzeuge"] = n["art"] == "llm" and "tool_call_parser" in v
    if n["gpu_gib"] / total_gib > ANTEIL_MAX:
        raise Fehler("budget")
    return eigen_ok(n)


def eigen_aendern(mid, felder, total_gib, cfg, path=EIGENE, messung_path=MESSUNG):
    """Saves a changed recipe of an own entry; never of one that runs now (it would start differently than measured).
    Its measurement goes: the numbers belonged to the old recipe. Returns the new entry."""
    alle = [_alt_anteil(x) for x in eigene(path)]
    i = next((j for j, x in enumerate(alle) if x.get("id") == mid), None)
    if i is None:
        raise Fehler("unbekannt")
    kat = katalog()
    if any(jetzt_id(a, cfg, kat) == mid for a in TAUSCH):
        raise Fehler("aktiv")
    alt = {k: x for k, x in alle[i].items() if k != "zeit"}
    n = rezept_anwenden(alt, felder, total_gib)
    if n == alt:
        raise Fehler("schon")
    alle[i] = dict(n, zeit=alle[i].get("zeit", int(time.time())))
    write_json(path, {"modelle": alle}, indent=1)
    messung = read_json(messung_path, {})
    if mid in (messung.get("modelle") or {}):
        del messung["modelle"][mid]
        write_json(messung_path, messung, indent=1)
    return n


def katalog_zeile(m, messung):
    """„In den Katalog übernehmen“: the own entry as a ready line for modelle.json (no "eigen", no time, the id without
    "eigen-"), pinned as it is; gemessen only when its last measurement went through."""
    if not m.get("eigen"):
        raise Fehler("eigen")
    r = (messung.get("modelle") or {}).get(m["id"]) or {}
    z = {k: x for k, x in m.items() if k not in ("eigen", "zeit")}
    z["id"] = m["id"][len("eigen-"):]
    z["gemessen"] = r.get("ok") is True
    pruefe_eintrag(z)
    return json.dumps(z, ensure_ascii=False, indent=2)


def eigene(path=None):
    return [m for m in read_json(path or EIGENE, {}).get("modelle") or [] if isinstance(m, dict)]


def eigen_speichern(m, path=None, kat=None):
    """Adds an own entry (checked again); refuses a second one for the same id or repository file, and more than
    EIGENE_MAX."""
    path = path or EIGENE
    eigen_ok(m)
    kat = katalog() if kat is None else kat
    alle = eigene(path)
    def schluessel(x):        # one repository may give several own files (GGUF quantizations), each once
        return x.get("repo"), (x.get("datei") or {}).get("path")
    if m["id"] in kat or any(schluessel(x) == schluessel(m) for x in alle) or any(schluessel(x) == schluessel(m) for x in kat.values()):
        raise Fehler("schon")
    if len(alle) >= EIGENE_MAX:
        raise Fehler("voll")
    write_json(path, {"modelle": alle + [dict(m, zeit=int(time.time()))]}, indent=1)


def eigen_loeschen(mid, cfg, now=None, path=EIGENE, wechsel=WECHSEL, hf_home=None):
    """Takes an own entry off the list; never one that runs or that can still be brought back (7 days). Returns its
    cache folder, which the caller removes (it belongs to the service user, like the whole cache)."""
    alle = eigene(path)
    m = next((x for x in alle if x.get("id") == mid), None)
    if m is None:
        raise Fehler("unbekannt")
    if any(jetzt_id(a, cfg) == mid for a in TAUSCH + ("klein",)):
        raise Fehler("aktiv")
    w = read_json(wechsel, {}).get(m.get("art")) or {}
    if w.get("alt") == mid and (time.time() if now is None else now) - float(w.get("zeit", 0)) <= ALT_TAGE * 86400:
        raise Fehler("frist")
    write_json(path, {"modelle": [x for x in alle if x.get("id") != mid]}, indent=1)
    return hf_ordner(m, hf_home)


def ordner_weg(ordner, hf_home=None):
    """Removes one model folder of the Hugging Face cache (never a link, never anything outside hub/models--*)."""
    import shutil
    hub = os.path.realpath(os.path.join(hf_wurzel(hf_home), "hub"))
    if os.path.islink(ordner) or not os.path.isdir(ordner):
        return False
    if os.path.dirname(os.path.realpath(ordner)) != hub or not os.path.basename(ordner).startswith("models--"):
        raise Fehler("ordner")
    shutil.rmtree(ordner)
    return True


# ---------------------------------------------------------------- Modell-Bibliothek (stage B1c, alzeo idea 2)
# Every model commit in the Hugging Face cache of this computer, with its size and who needs it: a catalog or own
# entry pins it (fest), it runs, or nothing names it (lose: an older commit left by an update, a model taken out of
# the catalog). Only a loose commit may go, after the admin confirmed it; ids and numbers only.
BIBLIOTHEK_MAX = 400


def _snap_bytes(snap):
    """Bytes of one snapshot: each file once (its blob), links followed only inside the cache (pruefen's rules)."""
    gesehen, n = set(), 0
    for root, _, files in os.walk(snap):
        for name in files:
            ziel = os.path.realpath(os.path.join(root, name))
            if ziel not in gesehen and os.path.isfile(ziel):
                gesehen.add(ziel)
                n += os.path.getsize(ziel)
    return n


def _wer_braucht(repo, rev, kat):
    """The ids of the entries that name this commit: pinned to it, or measured on the newest (no pinned commit), or
    an own recipe's drafter pinned to it."""
    out = []
    for mid, m in kat.items():
        v = m.get("vllm") if m.get("engine") == "vllm" else {}
        if (m.get("repo") == repo and m.get("revision") in (rev, "")) or (
                (v or {}).get("entwurf") == repo and (v or {}).get("entwurf_revision", rev) in (rev, "")):
            out.append(mid)
    return sorted(out)


def bibliothek(cfg, kat=None, hf_home=None):
    """[{repo, revision, gib, ids, laeuft, lose, geladen}] for every commit in the cache, biggest first (geladen: by
    „Nur herunterladen“, waiting for a slot of its program)."""
    kat = katalog() if kat is None else kat
    hub = os.path.join(hf_wurzel(hf_home), "hub")
    laufend = {x["id"] for x in aktiv(cfg, 0, kat)} | {jetzt_id(a, cfg, kat) for a in TAUSCH}
    unten = {(x["repo"], x["revision"]) for x in geladen()}
    out = []
    try:
        namen = sorted(os.listdir(hub))
    except OSError:
        return []
    for name in namen:
        ordner = os.path.join(hub, name)
        if not name.startswith("models--") or os.path.islink(ordner) or not os.path.isdir(ordner):
            continue
        repo = name[len("models--"):].replace("--", "/", 1)
        snaps = os.path.join(ordner, "snapshots")
        if not REPO.match(repo) or not os.path.isdir(snaps) or os.path.islink(snaps):
            continue
        for rev in sorted(os.listdir(snaps)):
            snap = os.path.join(snaps, rev)
            if not REV.match(rev) or os.path.islink(snap) or not os.path.isdir(snap):
                continue
            ids = _wer_braucht(repo, rev, kat)
            out.append({"repo": repo, "revision": rev, "gib": round(_snap_bytes(snap) / 2**30, 1), "ids": ids,
                        "laeuft": bool(set(ids) & laufend), "lose": not ids, "geladen": (repo, rev) in unten})
            if len(out) >= BIBLIOTHEK_MAX:
                break
    return sorted(out, key=lambda x: (-x["gib"], x["repo"], x["revision"]))


def lose_weg(repo, rev, cfg, kat=None, hf_home=None):
    """Removes one loose commit (bibliothek: no entry names it): its snapshot and the blobs of the model's folder that
    no other snapshot of it uses; the whole folder when it was the last. Never a link, never outside the cache.
    Returns the bytes freed; raises Fehler (repo, fehlt, gebraucht)."""
    import shutil
    if not REPO.match(str(repo)) or ".." in repo or not REV.match(str(rev)):
        raise Fehler("repo")
    kat = katalog() if kat is None else kat
    if _wer_braucht(repo, rev, kat):
        raise Fehler("gebraucht")
    laden_vergessen(repo, rev)
    ordner = hf_ordner({"repo": repo}, hf_home)
    snaps = os.path.join(ordner, "snapshots")
    snap = os.path.join(snaps, rev)
    if os.path.islink(ordner) or os.path.islink(snaps) or os.path.islink(snap) or not os.path.isdir(snap):
        raise Fehler("fehlt")
    andere = [os.path.join(snaps, r) for r in os.listdir(snaps) if r != rev and REV.match(r)]
    if not andere:
        frei = _snap_bytes(snap)
        ordner_weg(ordner, hf_home)
        return frei
    blobs = os.path.realpath(os.path.join(ordner, "blobs"))

    def eigene_blobs(s):
        out = set()
        for root, _, files in os.walk(s):
            for name in files:
                p = os.path.join(root, name)
                if os.path.islink(p):
                    erst = os.path.normpath(os.path.join(root, os.readlink(p)))
                    if os.path.realpath(os.path.dirname(erst)) == blobs:
                        out.add(os.path.basename(erst))
        return out
    bleiben = set().union(*(eigene_blobs(s) for s in andere))
    weg = eigene_blobs(snap) - bleiben
    frei = 0
    shutil.rmtree(snap)
    for b in weg:
        p = os.path.join(blobs, b)
        if os.path.isfile(p) and not os.path.islink(p):
            frei += os.path.getsize(p)
        if os.path.lexists(p):
            os.unlink(p)          # a link into the shared hub/blobs goes; what it points to stays
    return frei


# „Nur herunterladen“ (stage B1c, Dominik 2026-11-16 „alles mögliche gedownloaded werden“): any public model, or one
# whose terms the admin accepted (with the token), on a pinned commit, only the file kinds of ERLAUBT_LADEN (never
# Python code, never pickle), when it fits the disk. It is only on the disk (Bibliothek: „heruntergeladen“) until a
# slot for its program checks it; nothing runs it. „Nur laden“ fetches a catalog or own model the same way while the
# current one keeps running (alzeo idea 3). Both go as the wish „laden“ to the root unit speech-spark-wechsel.
GELADEN = os.path.join(STATE, "modelle-geladen.json")
GELADEN_MAX = 40
PLATTE_RESERVE_GIB = 20          # what a download leaves free on the disk at least


def geladen(path=None):
    """The models downloaded with „Nur herunterladen“: [{id, repo, revision, gib, lizenz, gewerblich, code, zeit}]."""
    return [x for x in read_json(path or GELADEN, {}).get("modelle", []) if isinstance(x, dict) and ID.match(str(x.get("id", "")))
            and REPO.match(str(x.get("repo", ""))) and REV.match(str(x.get("revision", "")))]


def platte_frei_gib(hf_home=None):
    import shutil
    ort = hf_wurzel(hf_home)
    while ort and not os.path.isdir(ort):
        ort = os.path.dirname(ort)
    return shutil.disk_usage(ort or "/").free / 2**30


def laden_vorschlag(info, repo, frei_gib, mit_token=False):
    """What „Nur herunterladen“ would fetch from the metadata of one commit: the entry, or Fehler (repo, antwort,
    zugang, format, platte)."""
    import fnmatch
    if not REPO.match(str(repo)) or ".." in repo:
        raise Fehler("repo")
    if not isinstance(info, dict) or not REV.match(str(info.get("sha", ""))):
        raise Fehler("antwort")
    _zugang(info, mit_token)
    files = [x for x in info.get("siblings") or [] if isinstance(x, dict) and isinstance(x.get("rfilename"), str)]
    if len(files) > 2000:
        raise Fehler("format")
    nimmt = [x for x in files if not VERBOTEN.search(x["rfilename"])
             and any(fnmatch.fnmatch(x["rfilename"], e) for e in ERLAUBT_LADEN)]
    if not any(x["rfilename"].endswith(GEWICHTE_LADEN) for x in nimmt):
        raise Fehler("format")
    def size(x):
        lfs = x.get("lfs") if isinstance(x.get("lfs"), dict) else {}
        v = lfs.get("size", x.get("size"))
        return v if isinstance(v, int) and not isinstance(v, bool) and v >= 0 else 0
    gib = sum(size(x) for x in nimmt) / 2**30
    if gib + PLATTE_RESERVE_GIB > frei_gib:
        raise Fehler("platte")
    cfg = info.get("config") if isinstance(info.get("config"), dict) else {}
    card = info.get("cardData") if isinstance(info.get("cardData"), dict) else {}
    lizenz = _wort(card.get("license") if isinstance(card.get("license"), str) else "", 32) or "unbekannt"
    mid = ("hf-" + _wort(repo.split("/", 1)[1], 34)).rstrip("-.") + "-" + info["sha"][:8]
    return {"id": mid, "repo": repo, "revision": info["sha"], "gib": round(gib, 1), "lizenz": lizenz,
            "gewerblich": lizenz in FREI, "code": any(w in json.dumps(cfg) for w in ('"auto_map"', "trust_remote_code"))}


def laden_merken(e, path=None, kat=None):
    """Keeps a „Nur herunterladen“ entry (once per repository and commit, at most GELADEN_MAX)."""
    kat = katalog() if kat is None else kat
    alle = geladen(path)
    if any(x["repo"] == e["repo"] and x["revision"] == e["revision"] for x in alle) or _wer_braucht(e["repo"], e["revision"], kat):
        raise Fehler("schon")
    if len(alle) >= GELADEN_MAX:
        raise Fehler("voll")
    write_json(path or GELADEN, {"modelle": alle + [dict(e, zeit=int(time.time()))]}, indent=1)


def laden_vergessen(repo, rev, path=None):
    alle = geladen(path)
    rest = [x for x in alle if not (x["repo"] == repo and x["revision"] == rev)]
    if len(rest) != len(alle):
        write_json(path or GELADEN, {"modelle": rest}, indent=1)


def laden_ziel(mid, kat=None, path=None):
    """What the wish „laden <id>“ fetches: (repo, revision, erlaubt, gewichte) of a catalog or own entry (its own rules,
    with its drafter by vorbereiten) or of a „Nur herunterladen“ entry; Fehler("unbekannt") otherwise."""
    kat = katalog() if kat is None else kat
    if mid in kat and kat[mid].get("repo") and kat[mid]["engine"] in ENTFERNBAR:
        return kat[mid]
    e = next((x for x in geladen(path) if x["id"] == mid), None)
    if e is None:
        raise Fehler("unbekannt")
    return e


def laden_anfragen(mid, starten, laeuft=False, kat=None):
    """„Nur laden“ / „Nur herunterladen“: the wish for root, then starten() starts WECHSEL_UNIT. Raises Fehler
    (laeuft, unbekannt, start)."""
    if laeuft:
        raise Fehler("laeuft")
    laden_ziel(mid, kat)
    wunsch_schreiben("laden", mid)
    if not starten():
        raise Fehler("start")


def herunterladen_anfragen(repo, rev, info, starten, laeuft=False, mit_token=False, frei_gib=None, kat=None):
    """„Nur herunterladen“ on the computer the models run on: the metadata's rules (laden_vorschlag), the entry kept,
    then the wish. Returns the entry; raises Fehler (laeuft, the rule's word, schon, voll, start)."""
    if laeuft:
        raise Fehler("laeuft")
    e = laden_vorschlag(info, repo, platte_frei_gib() if frei_gib is None else frei_gib, mit_token)
    if rev and e["revision"] != rev:
        raise Fehler("antwort")
    laden_merken(e, kat=kat)
    laden_anfragen(e["id"], starten, kat=kat)
    return e


def laden_lauf(mid, log=print, hf_home=None):
    """Root's unit (as the panel's user) fetches and checks one model: again only when it still fits the disk."""
    z = laden_ziel(mid)
    if "engine" in z:                                   # a catalog or own entry: its own way, drafter included
        vorbereiten(z, hf_home)
    else:
        if z["gib"] + PLATTE_RESERVE_GIB > platte_frei_gib(hf_home):
            raise Fehler("platte")
        _laden(z["repo"], z["revision"], hf_ordner(z, hf_home), ERLAUBT_LADEN, GEWICHTE_LADEN)
    log(f"modelle: laden {mid} ok")


# ---------------------------------------------------------------- command line
def _opt(args, name, default=""):
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else default


def cli(args, log=print):
    """Returns the exit code: 0 ok, 2 wrong call or catalog, 3 the measurement failed."""
    try:
        cmd = args[0] if args else ""
        if cmd == "liste":
            for mid, m in katalog().items():
                log(f"{mid:27} {m['art']:6} {m['need_gib']:>3} GiB  {'fest' if m['revision'] else 'offen'}  {m['name']['de']}")
            return 0
        if cmd == "wahl":
            for line in wahl_zeilen(args[1]):
                log(line)
            return 0
        if cmd == "wahl-keys":
            log(" ".join(m["wahl"] for m in wahl(args[1])))
            return 0
        if cmd == "gib":
            log(f"{eintrag(args[1])['need_gib']:g}")
            return 0
        if cmd == "feld":
            m = eintrag(args[1])
            if args[2] not in ("repo", "revision", "wahl"):
                raise Fehler("feld")
            log(m.get(args[2]) or "")
            return 0
        if cmd == "messliste":
            log(" ".join(messliste(args[1:])))
            return 0
        if cmd == "vllm-args":
            for a in vllm_args(eintrag(args[1]), int(_opt(args, "--port", MESS_PORT)), _opt(args, "--revision"),
                               mtp="--ohne-mtp" not in args):
                log(a)
            return 0
        if cmd == "docker-bild":
            log(docker_bild(eintrag(args[1])))
            return 0
        if cmd == "docker-args":
            m = eintrag(args[1])
            for a in docker_args(m, _opt(args, "--revision"), _opt(args, "--name"), int(_opt(args, "--uid")),
                                 int(_opt(args, "--gid")), mtp="--ohne-mtp" not in args):
                log(a)
            return 0
        if cmd == "vorbereiten":
            m = eintrag(args[1])
            rev = _opt(args, "--revision")
            if rev:                              # a switch: exactly the commit fest_revision() pins (stage E4)
                if not REV.match(rev) or rev != fest_revision(m):
                    raise Fehler("revision")
                m = dict(m, revision=rev)
            try:
                rev = vorbereiten(m)
            except Fehler:
                raise
            except Exception:
                print(f"modelle: nicht geladen {m['id']} download", flush=True)
                return 3
            print(f"modelle: geladen {m['id']} geprueft", file=sys.stderr, flush=True)
            log(rev)
            return 0
        if cmd == "anteil":                 # engine.sh: a speech engine's share for this computer's pool (sprach_anteil)
            if len(args) != 2 or not re.fullmatch(r"0?\.[0-9]{1,6}", args[1]):
                raise Fehler("anteil")
            log(f"{sprach_anteil(float(args[1])):.4f}")
            return 0
        if cmd == "sprach-eigen":           # engine.sh: is this repository an own speech model of this role's program?
            m = zum_repo(args[2]) if len(args) == 3 and args[1] in SPRACH else None
            ok = bool(m and m.get("eigen") and m["art"] == args[1] and m["engine"] == SPRACH[args[1]][0])
            log("ja" if ok else "nein")
            return 0 if ok else 1
        if cmd == "fest":                   # install.sh dl, engine.sh: "<id> <commit>" of a pinned repository
            m = fest(args[1])
            log(f"{m['id']} {m['revision']}")
            return 0
        if cmd == "erlaubt":                # install.sh dl: the file kinds a download may take
            log(json.dumps(list(ERLAUBT)))
            return 0
        if cmd == "pruefen":
            m = eintrag(args[1])
            n, size = pruefen(hf_ordner(m), args[2] if len(args) > 2 else m["revision"])
            log(f"modelle: geprueft {m['id']} {n} dateien {size // 2**30} GiB")
            return 0
        if cmd == "venv":
            log(venv(eintrag(args[1]) if args[1] not in ROLLEN else rolle(args[1], load_config())[0]))
            return 0
        if cmd == "kompilieren":
            for k, v in KOMPILIEREN.items():
                log(f"{k}={v}")
            return 0
        if cmd == "signatur":
            log(signatur(args[1], load_config()))
            return 0
        if cmd == "start-args":
            cfg = load_config()
            for a in start_args(args[1], cfg):
                log(a)
            start_merken(args[1], cfg)
            return 0
        if cmd == "laden":
            # root's unit: the wish's id checked again, then fetched and checked as the panel's user
            laden_lauf(args[1], log)
            return 0
        if cmd == "neustart-pruefen":
            # root checks again what the panel checked: the language model runs with other settings than its entry
            if not abweichung("llm", load_config()):
                raise Fehler("schon")
            log("neustart llm")
            return 0
        if cmd == "messen-lauf":
            m = eintrag(args[1])
            rev = _opt(args, "--revision")
            r = messen_lauf(m, int(_opt(args, "--port", MESS_PORT)), _opt(args, "--einheit"), log)
            if REV.match(rev) and rev == (m["revision"] or rev):
                r["revision"] = rev
            if "--ohne-mtp" in args:
                r["mtp"] = "aus"
            merke(m["id"], r)
            return 0 if r["ok"] else 3
        if cmd == "datei-laden":             # speech-spark.sh before the switch to an own picture or music file
            datei_laden(args[1], log=log)
            return 0
        if cmd == "dateiprobe":              # … and after it
            ok, wort = datei_probe(args[1])
            log(f"modelle: probe {args[1]} {'ok' if ok else 'fehler ' + wort}")
            return 0 if ok else 3
        if cmd == "sprachprobe":             # speech-spark.sh after the switch of an own speech model
            if args[1] not in SPRACH:
                raise Fehler("art")
            import bench
            ok, wort, anteil = bench.sprachprobe(log=lambda *a, **k: None)
            log(f"modelle: probe {args[1]} {'ok' if ok else 'fehler ' + wort}" + (f" {anteil:.2f}" if anteil is not None else ""))
            return 0 if ok else 3
        if cmd == "rundlauf":
            import llmstart
            ok, wort = rundlauf(load_config(), log, stufe=llmstart.stufe)
            if not ok:
                llmstart.stufe("fehler", grund=wort)
            log(f"modelle: rundlauf {'ok' if ok else 'fehler ' + wort}")
            return 0 if ok else 3
        if cmd == "jetzt":
            log(jetzt_id(args[1], load_config()) or "-")
            return 0
        if cmd == "wechsel-pruefen":
            # root checks again what the panel checked
            m = wechsel_pruefen(args[1], args[2], load_config(), gesamt_gib())
            log(wechsel_weg(args[1], m))
            return 0
        if cmd == "wechsel-schalten":
            if args[1] not in ROLLEN and args[1] not in SPRACH and args[1] not in DATEI_ART:
                raise Fehler("art")
            _schreib(mit_wechsel(_roh(), args[1], eintrag(args[2])))
            log(f"modelle: schalter {args[1]} {args[2]}")
            return 0
        if cmd == "wechsel-merken":
            if args[1] not in TAUSCH or not ID.match(args[3]) or not (args[2] == "-" or ID.match(args[2])):
                raise Fehler("aufruf")
            if args[2] != "-":
                wechsel_merken(args[1], args[2], args[3])
            return 0
        if cmd == "zurueck-ziel":
            log(zurueck_ziel(args[1]))
            return 0
        if cmd == "entfernbar":
            log(entfernbar(args[1], load_config()))
            return 0
        if cmd == "platz-pruefen":            # root checks again what the panel checked
            platz_pruefen(args[1], load_config(), gesamt_gib())
            return 0
        if cmd == "platz-jetzt":
            log(load_config().get("llm", {}).get("platz") or "standard")
            return 0
        if cmd == "platz-schalten":           # also back to the one before (no budget check: it ran before)
            if args[1] not in PLATZ:
                raise Fehler("platz")
            raw = _roh()
            raw.setdefault("llm", {})["platz"] = args[1]
            _schreib(raw)
            log(f"modelle: schalter platz {args[1]}")
            return 0
        if cmd == "wunsch-schreiben":
            wunsch_schreiben(args[1], args[2])
            return 0
        if cmd == "wunsch-nehmen":
            log(" ".join(wunsch_nehmen()))
            return 0
        if cmd == "messen-wunsch-nehmen":
            log(" ".join(messen_wunsch_nehmen()))
            return 0
        if cmd == "ergebnis":
            data, kat = read_json(MESSUNG, {}), katalog()
            for mid, r in (data.get("modelle") or {}).items():
                if mid in kat:                      # an entry taken out of the catalog keeps no line (Flash Next 0.65)
                    log(zeile(mid, r))
            return 0
    except Fehler as e:
        print(f"modelle: abgelehnt {e}", flush=True)
        return 2
    except (IndexError, ValueError):
        print("modelle: abgelehnt aufruf", flush=True)
        return 2
    except OSError:
        print("modelle: abgelehnt datei", flush=True)
        return 2
    print("modelle: abgelehnt aufruf", flush=True)
    return 2


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:], log=lambda s: print(s, flush=True)))
