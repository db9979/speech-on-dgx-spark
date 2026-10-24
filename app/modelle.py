"""Modell-Katalog (plan plaene/eigene-modelle.md, Dominik 2026-10-14 „1a 2a 3a 4a 5a 6a“): the models this
installation runs itself, one line each in modelle.json, read only here.

Stage E0 measures before anything switches: `sudo speech-spark modelle messen [llm] [sehen] [fp8] [gemma] [kolibri] [vl30]
[dspark] [flash]` stops the
qwen38 lanes for a while (with a Wartungspause), starts one catalog model at a time natively with vLLM on
127.0.0.1:MESS_PORT and measures it with fixed German questions, one tool call and fixed test pictures, then
starts qwen38 again. The result goes to STATE/modelle-messung.json and into the journal ("modelle:" lines with
fixed words and numbers, never an answer's text). Nothing is switched by a measurement and nothing is deleted.
A main model candidate is also measured with 2 and 4 long questions at once and one question of about 60K tokens, and
the engine's own count of the context room (Dominik 2026-10-17: 2-4 at once with a context of 64K or more).

A variant ("basis": an earlier entry's id) takes that entry and changes only the fields it names, its vllm fields
merged (one source: Qwen3.8 with the DSpark helper model). A helper model
(vllm "entwurf") is a second repository with a pinned commit, fetched and checked like the main one.

Rules for every entry (test_modelle): the engine is one we know, the repository a plain "owner/name", the revision
a full commit or empty (empty only to measure), the memory share at most ANTEIL_MAX (above ~0.80 the GB10 freezes),
never trust_remote_code, only the flags vllm_args builds from the fields in VLLM_KEYS. Downloads take only the
file kinds in ERLAUBT (no pickle, no Python code) and pruefen() checks every file against its name in the
Hugging Face cache (SHA-256 for large files, the git blob hash for small ones).

Command line (as the panel's service user, from speech-spark.sh): liste · feld <id> repo|revision · messliste <was …> · vorbereiten <id> ·
pruefen <id> [revision] · vllm-args <id> [--port N] [--revision R] [--ohne-mtp] · messen-lauf <id> [--port N]
[--einheit unit] [--revision R] · ergebnis · venv <id>|llm|sehen · start-args llm|sehen (engine.sh) · signatur llm|sehen
(install.sh) · docker-bild <id> · docker-args <id> --revision R --name N --uid U --gid G [--ohne-mtp] (mess_docker) ·
fest <repo> · erlaubt (install.sh dl, engine.sh: the pinned commit of a speech model and the file kinds to fetch).

An entry with a Docker recipe (vllm "docker", DOCKER) runs as a container only while it is measured (Dominik
2026-10-17: Docker only on tars, only for model engines): pinned image, no network, its socket put on 127.0.0.1 by
dockertor.py; switching to it is the next stage.

Stage E2 starts the own language model: speech-spark-llm (engine.sh llm) and, on demand, speech-spark-sehen
(engine.sh sehen) run `vllm serve` with start_args(): config llm.modell / llm.sehen_modell, a pinned commit only
(the catalog's or the one `modelle messen` checked), on 127.0.0.1 behind the LLM-Tor (llm_tor.py, llm.port).
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
from common import STATE, load_config, mem_available_gib, read_json, write_json  # noqa: E402

KATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modelle.json")
MESSUNG = os.path.join(STATE, "modelle-messung.json")
VORHER = os.path.join(STATE, "qwen38-vorher.json")    # stage E3: what `modelle llm uebernehmen` switched off
QWEN38_KEINE = ("qwen38-dashboard",)                     # qwen38 units that are no model; they keep running
ARTEN = {"llm": ("Sprachmodell", "Language model"), "sehen": ("Bildverständnis", "Image understanding"),
         "asr": ("Spracherkennung", "Speech recognition"), "tts": ("Sprachausgabe", "Speech output"),
         "bild": ("Bilder malen", "Painting pictures"), "musik": ("Musik machen", "Making music"),
         "klein": ("Kleine Modelle (CPU)", "Small models (CPU)")}
# vllm: an engine this installation starts itself (the strict rules below); the others are run as before by their
# own services and are listed for the budget: extern (qwen38), the speech models, sd.cpp, acestep.cpp, ONNX on the CPU
ENGINES = ("vllm", "extern", "qwen-asr", "qwen-tts", "sdcpp", "acestepcpp", "onnx-cpu")
BETRIEB = ("resident", "bei_bedarf")
MESSEN = ("immer", "auf_wunsch")
ANTEIL_MAX = 0.80
MESS_PORT = 31016
VLLM_KEYS = ("reasoning_parser", "tool_call_parser", "mtp", "max_seqs", "quantization", "bilder_pro_frage", "kv_cache_dtype", "entwurf",
             "venv", "docker")
VENVS = ("llm", "kolibri")       # $PREFIX/venv-<name>: venv-llm (install.sh --llm), venv-kolibri (install.sh --kolibri)
KV = ("fp8",)
# speculative decoding with a helper model (vllm "entwurf"): the method and its fixed extra settings for vLLM
ENTWURF = {"dspark": {"draft_sample_method": "probabilistic"}}
LOGPROBS_MAX = 20                # top_logprobs an engine started here gives (--max-logprobs; System One in llm_tor.py)
ROLLEN = {"llm": ("modell", "engine_port", 31016), "sehen": ("sehen_modell", "sehen_port", 31017)}   # config llm.*
ANFRAGE_KEYS = ("chat_template_kwargs", "top_k")
# the only file kinds a model download takes: weights as safetensors, the rest is text; never *.bin/*.pt/*.pkl
ERLAUBT = ("*.safetensors", "*.json", "*.txt", "*.jinja", "*.model", "*.tiktoken", "*.md", "LICENSE*")
VERBOTEN = re.compile(r"(?i)\.(bin|pt|pth|pkl|pickle|ckpt|py|pyc|so|sh)$")
REPO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}/[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
REV = re.compile(r"^[0-9a-f]{40}$")
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
    if not (m["engine"] == "extern" and m.get("repo") == "") and (not REPO.match(str(m.get("repo", ""))) or ".." in m["repo"]):
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
    if "trust_remote_code" in json.dumps(m):
        raise Fehler("trust_remote_code")
    if m["engine"] == "vllm":
        _pruefe_vllm(m)
    return m


def _pruefe_vllm(m):
    """An engine started by this installation: only llm or sehen, a memory share within ANTEIL_MAX, only the known
    flags and request fields."""
    if m["art"] not in ("llm", "sehen") or m.get("messen") not in MESSEN:
        raise Fehler("art")
    a = m.get("anteil")
    if isinstance(a, bool) or not isinstance(a, (int, float)) or not 0.02 <= a <= ANTEIL_MAX:
        raise Fehler("anteil")
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
    v, q = m.get("vllm"), m.get("anfrage")
    if not isinstance(v, dict) or set(v) - set(VLLM_KEYS) or not isinstance(q, dict) or set(q) - set(ANFRAGE_KEYS):
        raise Fehler("felder")
    for key in ("reasoning_parser", "tool_call_parser"):
        if key in v and not PARSER.match(str(v[key])):
            raise Fehler(key)
    for key, hi in (("mtp", 8), ("max_seqs", 64), ("bilder_pro_frage", 8)):
        if key in v and (isinstance(v[key], bool) or not isinstance(v[key], int) or not 0 <= v[key] <= hi):
            raise Fehler(key)
    if "quantization" in v and v["quantization"] not in QUANT:
        raise Fehler("quantization")
    if "kv_cache_dtype" in v and v["kv_cache_dtype"] not in KV:
        raise Fehler("kv_cache_dtype")
    if v.get("venv", "llm") not in VENVS:
        raise Fehler("venv")
    if "docker" in v and (v["docker"] not in DOCKER or m["art"] != "llm" or "venv" in v or "entwurf" in v):
        raise Fehler("docker")
    if "entwurf" in v:
        e = v["entwurf"]
        if not isinstance(e, dict) or set(e) != {"methode", "repo", "revision", "tokens"} or e["methode"] not in ENTWURF:
            raise Fehler("entwurf")
        if not REPO.match(str(e["repo"])) or ".." in e["repo"] or not REV.match(str(e["revision"])):
            raise Fehler("entwurf")
        if isinstance(e["tokens"], bool) or not isinstance(e["tokens"], int) or not 1 <= e["tokens"] <= 16 or v.get("mtp"):
            raise Fehler("entwurf")


def _aus_bildmodell(m):
    """A picture entry (engine sdcpp) or a music entry (acestepcpp) takes name, licence, memory, repository and disk
    size from bildmodell.VARIANTS or musikmodell.VARIANTS: the files with their checksums live there, and install.sh
    hands those files alone to the service user."""
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
    return {**b, **m, "vllm": {**b["vllm"], **m.get("vllm", {})}, "anfrage": {**b["anfrage"], **m.get("anfrage", {})}}


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


def zur_variante(art, v, kat=None):
    """The entry of a picture variant or a small model's size (field "variante")."""
    kat = katalog() if kat is None else kat
    return next((m for m in kat.values() if m["art"] == art and v and m.get("variante") == v), None)


def _url_qwen38(url):
    """True when the language model's address is qwen38's own range on this machine (ports 30000-30099)."""
    m = re.match(r"^https?://(127\.0\.0\.1|localhost)(?::(\d+))?(/|$)", str(url or ""))
    return bool(m) and 30000 <= int(m.group(2) or 0) <= 30099


def aktiv(cfg, total_gib, lanes=(), kat=None):
    """The models the configuration runs now: [{id, art, gib, betrieb}], gib from the engines' memory shares where
    the configuration sets them (vLLM), else from the catalog. lanes: the memory shares of the running qwen38 lanes."""
    kat = katalog() if kat is None else kat
    out = []

    def add(m, gib=None, betrieb=None):
        if m:
            out.append({"id": m["id"], "art": m["art"], "gib": round(float(gib if gib is not None else m["need_gib"]), 1),
                        "betrieb": betrieb or m["betrieb"]})
    chat = cfg.get("chat", {})
    if _url_qwen38(chat.get("llm_url")):
        share = sum(f for f in lanes if f)
        add(kat.get("qwen38-extern"), share * total_gib if share else None)
    own = cfg.get("llm", {})
    if own.get("enabled"):
        m = kat.get(own.get("modell"))
        m = _platz(m, cfg) if m and m["engine"] == "vllm" and m["art"] == "llm" else m
        add(m, m["anteil"] * total_gib + 1.5 if m and m["engine"] == "vllm" else None)
        if m and not m.get("kann_sehen"):
            add(kat.get(own.get("sehen_modell")), None, "bei_bedarf")
    a = cfg.get("asr", {})
    if a.get("enabled"):
        if a.get("recognizer") == "parakeet":
            add(kat.get("parakeet-primeline"))
        else:
            gib = a["engine_mem"] * total_gib + 1.5 if a.get("backend") == "vllm" and "engine_mem" in a else None
            add(zum_repo(a.get("model"), kat), gib)
            if a.get("timestamps"):
                add(zum_repo(a.get("aligner_model"), kat))
    t = cfg.get("tts", {})
    if t.get("enabled"):
        omni = t.get("backend") == "vllm-omni" and "engine_mem_talker" in t
        gib = (t["engine_mem_talker"] + t.get("engine_mem_code2wav", 0)) * total_gib + 1.5 if omni else None
        add(zum_repo(t.get("model"), kat), gib)
        if t.get("voicedesign_enabled"):
            add(zum_repo(t.get("voicedesign_model"), kat), gib)
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
SYSTEM_GIB = 6     # DGX OS, the panel and the small services next to the models (plan: Speicher-Budget)


def budget(cfg, total_gib, lanes=(), kat=None):
    """The memory budget (plan „Speicher-Budget“): fixed = the resident models + system + reserve; on demand = the
    models loaded when needed. "alle" when all of them fit at once, "ein_platz" when only one on-demand model fits
    beside the fixed ones (they then run one after the other through vorrang), "zu_knapp" when not even that fits.
    A fixed rule from numbers; the model decides nothing."""
    teile = aktiv(cfg, total_gib, lanes, kat)
    reserve = float(cfg.get("memory", {}).get("reserve_gib", 10))
    fest = round(sum(x["gib"] for x in teile if x["betrieb"] == "resident"), 1)
    # pictures and music share one place (Dominik 2026-10-18 „immer nur ein Modell, beide nicht gleichzeitig“):
    # the bigger of the two counts, never both
    bedarf = [x["gib"] for x in teile if x["betrieb"] == "bei_bedarf" and x["art"] not in EIN_PLATZ]
    bedarf += [max(x["gib"] for x in teile if x["betrieb"] == "bei_bedarf" and x["art"] in EIN_PLATZ)] \
        if any(x["betrieb"] == "bei_bedarf" and x["art"] in EIN_PLATZ for x in teile) else []
    frei = round(total_gib - SYSTEM_GIB - reserve - fest, 1)
    if frei >= sum(bedarf):
        regel = "alle"
    elif frei >= max(bedarf, default=0):
        regel = "ein_platz"
    else:
        regel = "zu_knapp"
    return {"gesamt": round(total_gib, 1), "system": SYSTEM_GIB, "reserve": reserve, "fest": fest,
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
    """The ids to measure, in catalog order: was = words llm, sehen (the entries marked "immer"), fp8, gemma, kolibri,
    vl30, dspark (one entry each that is measured only on request), qwen36 (Qwen3.6 35B A3B NVFP4 with and without MTP),
    flash (Qwen3.8 Flash Next in Docker at both memory shares); no word means llm and sehen."""
    kat = katalog() if kat is None else kat
    was = list(was) or ["llm", "sehen"]
    wunsch = {"fp8": ("qwen38-27b-fp8",), "gemma": ("gemma-4-26b-a4b",), "kolibri": ("kolibri-1-nvfp4",),
              "vl30": ("qwen3-vl-30b-a3b-fp8",), "dspark": ("qwen38-27b-nvfp4-dspark",),
              "qwen36": ("qwen36-35b-a3b-nvfp4", "qwen36-35b-a3b-nvfp4-ohne-mtp"),     # Dominik 2026-10-18 „ja 1“
              "flash": ("qwen38-flash-next-fp4",)}     # Docker; share 0.65 never started (tars 2026-10-21)
    wunsch.update({i: (i,) for i, m in kat.items() if m.get("eigen") or docker_bild(m)})   # an own model by its id
    if any(w not in ("llm", "sehen") and w not in wunsch for w in was):
        raise Fehler("was")
    ids = [i for x in was for i in wunsch.get(x, ())]
    return [i for i, m in kat.items() if m["engine"] == "vllm" and (i in ids or (m["art"] in was and m["messen"] == "immer"))]


def vllm_args(m, port=MESS_PORT, revision="", mtp=True, uds=""):
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
    v = m["vllm"]
    a = [m["repo"], "--revision", rev, *(["--uds", uds] if uds else ["--host", "127.0.0.1", "--port", str(port)]),
         "--served-model-name", m["id"], "--max-model-len", str(m["kontext"]),
         "--gpu-memory-utilization", f"{m['anteil']:.2f}", "--max-num-seqs", str(v.get("max_seqs", 8)),
         "--generation-config", "vllm", "--no-enable-flashinfer-autotune",
         "--disable-uvicorn-access-log",   # stats stay on: /metrics counts the MTP and prefix cache hits
         # usage.prompt_tokens_details.cached_tokens: the panel shows how much of a question came from the prefix cache
         # (chat.timing_lines, verbrauch.py); the cache itself is on by default in vLLM V1
         "--enable-prompt-tokens-details"]
    if v.get("quantization"):
        a += ["--quantization", v["quantization"]]
    if v.get("kv_cache_dtype"):
        a += ["--kv-cache-dtype", v["kv_cache_dtype"]]
    if v.get("reasoning_parser"):
        a += ["--reasoning-parser", v["reasoning_parser"]]
    if v.get("tool_call_parser"):
        a += ["--tool-call-parser", v["tool_call_parser"], "--enable-auto-tool-choice"]
    if m["kann_sehen"]:      # a text-only model (Kolibri) gets no picture flag at all
        a += ["--limit-mm-per-prompt.image", str(v.get("bilder_pro_frage", 2))]
    if mtp and v.get("mtp"):
        a += ["--speculative-config", json.dumps({"method": "mtp", "num_speculative_tokens": v["mtp"]})]
    if v.get("entwurf"):     # the helper model from the cache (offline), its commit pinned; never measured without it
        if not mtp:
            raise Fehler("entwurf")
        e = v["entwurf"]
        a += ["--speculative-config", json.dumps({"method": e["methode"], "model": e["repo"], "revision": e["revision"],
                                                  "num_speculative_tokens": e["tokens"], **ENTWURF[e["methode"]]})]
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
    hf = os.path.realpath(hf_home or os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface"))
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
# (extra memory share, longest question in tokens; None = the catalog's). It is one pool: about 15 GiB hold 4
# conversations of 64K or one of 256K (Qwen3.8 NVFP4 on tars: 7.7 GiB for 131K, the KV cache already in FP8)
PLATZ = {"standard": (0.0, None), "4x64k": (0.07, 65536), "1x256k": (0.07, 262144)}
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
    return dict(m, anteil=round(min(m["anteil"] + plus, ANTEIL_MAX), 2), kontext=kontext)


def _platz(m, cfg):
    """mit_platz for the engine that starts: a choice this model does not allow (after a switch) counts as standard."""
    try:
        return mit_platz(m, cfg.get("llm", {}).get("platz"))
    except Fehler:
        return m


def platz_pruefen(platz, cfg, total_gib, lanes=(), kat=None):
    """The fixed rules for „Lange Gespräche“: a known choice, after the move, one the model allows, not the one set, and
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
    if budget(probe, total_gib, lanes, kat)["regel"] == "zu_knapp":
        raise Fehler("budget")
    return neu


def platz_wahl(cfg, total_gib, lanes=(), kat=None):
    """For the page: the choices with their extra memory and why one is not possible (a fixed word, "" when it is)."""
    c = cfg.get("llm", {})
    m = (kat or katalog()).get(c.get("modell"))
    out = []
    for p, (plus, _) in PLATZ.items():
        try:
            if m is None:
                raise Fehler("aus")
            platz_pruefen(p, cfg, total_gib, lanes, kat)
            nein = ""
        except Fehler as e:
            nein = str(e)
        out.append({"id": p, "name": PLATZ_NAMEN[p], "plus_gib": round(plus * total_gib, 1), "nein": nein})
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
    if m["vllm"].get("entwurf"):
        e = m["vllm"]["entwurf"]
        pruefen(hf_ordner(e, hf_home), e["revision"], hashes=False)
        zeiger(hf_ordner(e, hf_home), e["revision"])
    return vllm_args(m, port, rev) + ["--max-logprobs", str(LOGPROBS_MAX)]


# ---------------------------------------------------------------- files in the Hugging Face cache
def hf_ordner(m, hf_home=None):
    hf_home = hf_home or os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface")
    return os.path.join(hf_home, "hub", "models--" + m["repo"].replace("/", "--"))


def _datei_hash(path, algo, kopf=b""):
    h = hashlib.new(algo)
    h.update(kopf)
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 22), b""):
            h.update(block)
    return h.hexdigest()


def pruefen(ordner, rev, hashes=True):
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
            weights = weights or name.endswith(".safetensors")
            n += 1
            size += os.path.getsize(ziel)
    if not weights:
        raise Fehler("gewichte")
    return n, size


def _aufraeumen(ordner, rev):
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
            if os.path.islink(p) and (VERBOTEN.search(name) or not any(fnmatch.fnmatch(rel, e) for e in ERLAUBT)):
                os.unlink(p)
                n += 1
    return n


def _laden(repo, rev, ordner):
    """One repository's commit in the cache, checked; downloads only the ERLAUBT kinds when the check fails."""
    if rev:
        try:
            pruefen(ordner, rev)
            zeiger(ordner, rev)
            return rev
        except Fehler:
            weg = _aufraeumen(ordner, rev)
            if weg:
                print(f"modelle: {weg} alte dateien entfernt", flush=True)
    from huggingface_hub import snapshot_download
    path = snapshot_download(repo, revision=rev or None, allow_patterns=list(ERLAUBT))
    commit = os.path.basename(os.path.normpath(path))
    if rev and commit != rev:
        raise Fehler("revision")
    pruefen(ordner, commit)
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
    Returns whether anything changed."""
    if not REV.match(rev or "") or not os.path.isdir(os.path.join(ordner, "snapshots", rev)):
        raise Fehler("revision")
    neu = False
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
    commit. A pinned revision is fetched exactly; an empty one takes the newest commit (only to measure). A helper
    model (vllm "entwurf") always has its own pinned commit and is fetched and checked the same way."""
    commit = _laden(m["repo"], m["revision"], hf_ordner(m, hf_home))
    e = (m.get("vllm") or {}).get("entwurf")
    if e:
        _laden(e["repo"], e["revision"], hf_ordner(e, hf_home))
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
    r = {"art": m["art"], "repo": m["repo"], "anteil": m["anteil"], "kontext": m["kontext"], "zeit": int(time.time()),
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


# ---------------------------------------------------------------- the move (stage E3)
CHAT_FELDER = ("llm_url", "llm_key", "llm_key_from", "llm_model")


def _roh():
    """The configuration file as it is (without the shipped defaults merged in), for a small change."""
    from common import CONFIG_PATH
    with open(CONFIG_PATH) as f:
        return json.load(f)


def _schreib(raw):
    from common import CONFIG_PATH
    write_json(CONFIG_PATH, raw, indent=2)


def tor_url(cfg):
    from common import model_url
    return model_url("llm", "/v1", cfg)


def merken(units, cfg, path=VORHER):
    """Notes the running qwen38 units and the chat's model address before the move. Refuses a second move."""
    if cfg.get("llm", {}).get("enabled") or os.path.exists(path):
        raise Fehler("schon")
    if any(not re.fullmatch(r"qwen38-[a-z0-9-]{1,40}\.service", u) for u in units):
        raise Fehler("unit")
    chat = cfg.get("chat", {})
    write_json(path, {"units": list(units), "chat": {k: chat[k] for k in CHAT_FELDER if k in chat}, "zeit": int(time.time())},
               indent=1)


def vorher(path=VORHER):
    data = read_json(path, {})
    units = [u for u in data.get("units") or [] if re.fullmatch(r"qwen38-[a-z0-9-]{1,40}\.service", str(u))]
    return units, data.get("chat") or {}


def schalten(was, raw, path=VORHER):
    """The configuration for one step of the move: an = the own engine and door run (llm.enabled), um = the chat talks
    to the door (its key is api.key, llm.key), zurueck = everything as noted before the move. Returns the new raw."""
    raw = json.loads(json.dumps(raw))
    llm = raw.setdefault("llm", {})
    chat = raw.setdefault("chat", {})
    if was == "an":
        llm["enabled"] = True
    elif was == "um":
        if not llm.get("enabled"):
            raise Fehler("aus")
        merged = load_config()
        chat.update(llm_url=tor_url(merged), llm_key="", llm_model="")
        chat.pop("llm_key_from", None)
    elif was == "zurueck":
        _, alt = vorher(path)
        llm["enabled"] = False
        if alt:
            for k in CHAT_FELDER:
                if k in alt:
                    chat[k] = alt[k]
                else:
                    chat.pop(k, None)
    else:
        raise Fehler("was")
    return raw


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
WECHSEL_UNIT = "speech-spark-wechsel"
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
TAUSCH = ("llm", "sehen", "asr", "tts", "bild")          # the kinds that switch (small CPU models come with features)
INSTALL = {"asr": "--asr", "tts": "--tts", "bild": "--bild"}   # kinds install.sh sets up (wahl = its short key)
ENTFERNBAR = ("vllm", "qwen-asr", "qwen-tts")           # models that live in the Hugging Face cache


def gesamt_gib():
    """The unified memory of this machine in GiB."""
    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30


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
    elif art == "bild":
        c.setdefault("image", {})["variant"] = m["wahl"]
    return c


def wechsel_pruefen(art, mid, cfg, total_gib, lanes=(), kat=None, messung=None):
    """The fixed rules of a switch (the panel decides, never a model): a kind that switches, an entry of that kind from
    the catalog, for an own engine a pinned commit (catalog or measured), for the others an entry install.sh offers,
    the language model only after the move (`modelle llm uebernehmen`), not the one running, and the budget must not
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
    elif not m.get("wahl"):
        raise Fehler("wahl")
    if m.get("eigen") and art == "sehen":      # stage E5: no round trip on demand, so an own one is measured first
        messung = read_json(MESSUNG, {}) if messung is None else messung
        if not ((messung.get("modelle") or {}).get(mid) or {}).get("ok"):
            raise Fehler("ungeprueft")
    if jetzt_id(art, cfg, kat) == mid:
        raise Fehler("schon")
    if budget(mit_wechsel(cfg, art, m), total_gib, lanes, kat)["regel"] == "zu_knapp":
        raise Fehler("budget")
    return m


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
    within the 7 days to bring it back, never qwen38's own model. Returns the folder; raises Fehler."""
    kat = katalog() if kat is None else kat
    m = eintrag(mid, kat)
    if m["engine"] not in ENTFERNBAR or not m["repo"]:
        raise Fehler("art")
    # a variant shares its folder with its basis: none of the entries with this repository may run
    teilen = {i for i, x in kat.items() if x["repo"] == m["repo"]}
    if any(jetzt_id(a, cfg, kat) in teilen for a in TAUSCH) or any(x["id"] in teilen for x in aktiv(cfg, 0, (), kat)):
        raise Fehler("aktiv")
    w = read_json(path, {}).get(m["art"]) or {}
    if w.get("alt") == mid and (time.time() if now is None else now) - float(w.get("zeit", 0)) <= ALT_TAGE * 86400:
        raise Fehler("frist")
    ordner = hf_ordner(m, hf_home)
    if not os.path.isdir(ordner) or os.path.islink(ordner):
        raise Fehler("fehlt")
    return ordner


def _wunsch_ok(art, was):
    """A switch (a kind, an id or "zurueck") or „Lange Gespräche“ (art platz, one of PLATZ)."""
    return (art in TAUSCH and (was == "zurueck" or bool(ID.match(str(was))))) or (art == "platz" and was in PLATZ)


def wunsch_schreiben(art, was, path=WUNSCH):
    """The panel's wish (switch to an id, or "zurueck"; or art platz): checked again by root before anything happens."""
    if not _wunsch_ok(art, was):
        raise Fehler("wunsch")
    write_json(path, {"art": art, "was": was, "zeit": int(time.time())}, indent=1)


def wechsel_anfragen(art, was, cfg, total_gib, lanes, starten, laeuft=False):
    """A switch asked for (an id, or "zurueck" for the model before the last switch): the fixed rules, the wish for
    root, then starten() starts WECHSEL_UNIT. Used by the panel on this computer and by the Wärter (tarswart.py) for
    a panel on another one. Returns the entry; raises Fehler (laeuft, the rule's word, start)."""
    if laeuft:
        raise Fehler("laeuft")
    m = wechsel_pruefen(art, zurueck_ziel(art) if was == "zurueck" else was, cfg, total_gib, lanes)
    wunsch_schreiben(art, was)
    if not starten():
        raise Fehler("start")
    return m


def platz_anfragen(platz, cfg, total_gib, lanes, starten, laeuft=False):
    """„Lange Gespräche“ asked for: the fixed rules, the wish for root (art platz), then starten() starts WECHSEL_UNIT,
    which restarts the language model with it. Returns the entry as it will start; raises Fehler."""
    if laeuft:
        raise Fehler("laeuft")
    m = platz_pruefen(platz, cfg, total_gib, lanes)
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
HF_API = "https://huggingface.co/api/models/{repo}/revision/{rev}?blobs=true"
HF_INFO_MAX = 4 * 1024 * 1024    # bytes of the metadata answer at most
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
EIGEN_KONTEXT = 32768


def eigen_ok(m):
    """The extra rules for an own entry: an own id, an engine of this installation on a pinned commit, only measured
    on request, never a picture or speech model (those need their own code and come as catalog entries)."""
    pruefe_eintrag(m)
    if not (m.get("eigen") is True and str(m["id"]).startswith("eigen-") and m["engine"] == "vllm"
            and m["art"] in VLLM_ARCH and REV.match(m["revision"]) and m.get("messen") == "auf_wunsch"
            and m.get("vllm", {}).get("venv", "llm") == "llm" and not {"quantization", "docker"} & set(m.get("vllm", {}))):
        raise Fehler("eigen")
    return m


def _wort(text, n=40):
    return re.sub(r"[^a-z0-9.-]+", "-", str(text or "").lower()).strip("-.")[:n]


def eigen_vorschlag(info, art, repo, total_gib):
    """An own catalog entry from the Hugging Face metadata of one commit (the panel reads it, the model never):
    weights only as safetensors, no code from the repository, an architecture the engine knows, it must fit within
    ANTEIL_MAX. Returns the entry; raises Fehler with a fixed word."""
    if art not in VLLM_ARCH:
        raise Fehler("art")
    if not REPO.match(str(repo)) or ".." in repo:
        raise Fehler("repo")
    if not isinstance(info, dict) or not REV.match(str(info.get("sha", ""))):
        raise Fehler("antwort")
    if info.get("private") or info.get("gated") or info.get("disabled"):
        raise Fehler("zugang")
    files = [x for x in info.get("siblings") or [] if isinstance(x, dict) and isinstance(x.get("rfilename"), str)]
    weights = [x for x in files if x["rfilename"].endswith(".safetensors")]
    if not weights or len(files) > 2000:
        raise Fehler("format")
    cfg = info.get("config") if isinstance(info.get("config"), dict) else {}
    if any(w in json.dumps(cfg) for w in ('"auto_map"', "trust_remote_code")):     # also a tokenizer's own code
        raise Fehler("code")
    arch = (cfg.get("architectures") or [""])[0]
    if arch not in VLLM_ARCH[art] and not (art == "llm" and arch in VLLM_ARCH["sehen"]):
        raise Fehler("architektur")

    def size(x):
        lfs = x.get("lfs") if isinstance(x.get("lfs"), dict) else {}
        v = lfs.get("size", x.get("size"))
        return v if isinstance(v, int) and v >= 0 else None
    sizes = [size(x) for x in weights]
    if None in sizes:
        raise Fehler("format")
    gib = sum(sizes) / 2**30
    need = gib + KV_GIB[art]
    if need / total_gib > ANTEIL_MAX:
        raise Fehler("budget")
    sehen = arch in VLLM_ARCH["sehen"]
    fam = next((v for k, v in PARSER_FAMILIE.items() if arch.startswith(k)), {})
    card = info.get("cardData") if isinstance(info.get("cardData"), dict) else {}
    lizenz = _wort(card.get("license") if isinstance(card.get("license"), str) else "", 32) or "unbekannt"
    name = re.sub(r"[^A-Za-z0-9 ._-]+", "", repo.split("/", 1)[1])[:48] or "Modell"
    m = {"id": ("eigen-" + _wort(repo.split("/", 1)[1], 41)).rstrip("-."), "art": art, "name": {"de": name, "en": name},
         "engine": "vllm", "repo": repo, "revision": info["sha"], "lizenz": lizenz, "gewerblich": lizenz in FREI,
         "platte_gb": max(1, round(sum(sizes) / 1e9)), "need_gib": max(1, round(need)), "gemessen": False,
         "anteil": round(min(ANTEIL_MAX, max(0.02, need / total_gib + 0.01)), 2), "kontext": EIGEN_KONTEXT,
         "kann_sehen": sehen, "werkzeuge": art == "llm" and "tool_call_parser" in fam,
         "vllm": dict(fam if art == "llm" else {}, max_seqs=4), "anfrage": {}, "messen": "auf_wunsch",
         "betrieb": "resident" if art == "llm" else "bei_bedarf", "eigen": True}
    return eigen_ok(m)



# Zustand → Modelle „Suchen“ (Dominik 2026-10-17 „3a“): Hugging Face's public search for the language model or image
# understanding. The hits are data: each one only gets the quick rules below (the full check of eigen_vorschlag runs
# again on „Hinzufügen“, on the pinned commit), nothing is downloaded or added by searching.
HF_SUCHE = ("https://huggingface.co/api/models?search={q}&filter=safetensors&sort=downloads&direction=-1&limit=40"
            "&expand[]=config&expand[]=tags&expand[]=safetensors&expand[]=downloads&expand[]=cardData&expand[]=gated")
SUCHE_Q = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/-]{1,59}$")
SUCHE_MAX = 20
SUCHE_ANTWORT_MAX = 4 * 1024 * 1024
# bytes per weight of a dtype in the safetensors header (packed 4-bit formats come as U8 or I8)
DTYPE_BYTES = {"F64": 8, "I64": 8, "F32": 4, "I32": 4, "U32": 4, "BF16": 2, "F16": 2, "I16": 2, "U16": 2,
               "F8_E4M3": 1, "F8_E5M2": 1, "F8_E8M0": 1, "I8": 1, "U8": 1, "BOOL": 1}


def such_url(q):
    """The search address for an admin's words (letters, digits, space and ._/- only); Fehler("suche") otherwise."""
    q = str(q or "").strip()
    if not SUCHE_Q.match(q) or ".." in q:
        raise Fehler("suche")
    return HF_SUCHE.format(q=urllib.request.quote(q, safe=""))


def such_treffer(items, art, total_gib, kat=None):
    """The hits for the page: [{repo, downloads, lizenz, gb, need_gib, nein}], „nein“ a fixed word when a rule already
    says no (zugang, code, format, architektur, budget, schon); names that do not match REPO are dropped."""
    if art not in VLLM_ARCH:
        raise Fehler("art")
    if not isinstance(items, list):
        raise Fehler("antwort")
    kat = katalog() if kat is None else kat
    da = {m.get("repo") for m in kat.values()}
    out = []
    for x in items:
        if not isinstance(x, dict) or len(out) >= SUCHE_MAX:
            continue
        repo = x.get("id") if isinstance(x.get("id"), str) else ""
        if not REPO.match(repo) or ".." in repo:
            continue
        tags = [t for t in x.get("tags") or [] if isinstance(t, str)]
        cfg = x.get("config") if isinstance(x.get("config"), dict) else {}
        arch = (cfg.get("architectures") or [""])[0] if isinstance(cfg.get("architectures"), list) else ""
        st = x.get("safetensors") if isinstance(x.get("safetensors"), dict) else {}
        par = st.get("parameters") if isinstance(st.get("parameters"), dict) else {}
        byte = sum(v * DTYPE_BYTES.get(k, 2) for k, v in par.items() if isinstance(v, int) and v >= 0)
        gib = byte / 2**30 if byte else None
        need = round(gib + KV_GIB[art]) if gib is not None else None
        card = x.get("cardData") if isinstance(x.get("cardData"), dict) else {}
        lizenz = _wort(card.get("license") if isinstance(card.get("license"), str) else "", 32) or "unbekannt"
        if repo in da:
            nein = "schon"
        elif x.get("gated") or x.get("private") or x.get("disabled"):
            nein = "zugang"
        elif "custom_code" in tags or "auto_map" in json.dumps(cfg):
            nein = "code"
        elif "safetensors" not in tags and not par:
            nein = "format"
        elif arch not in VLLM_ARCH[art] and not (art == "llm" and arch in VLLM_ARCH["sehen"]):
            nein = "architektur"
        elif need is not None and need / total_gib > ANTEIL_MAX:
            nein = "budget"
        else:
            nein = ""
        d = x.get("downloads")
        out.append({"repo": repo, "downloads": d if isinstance(d, int) and d >= 0 else 0, "lizenz": lizenz,
                    "gewerblich": lizenz in FREI, "gb": round(byte / 1e9, 1) if byte else None, "need_gib": need,
                    "nein": nein})
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

def eigene(path=EIGENE):
    return [m for m in read_json(path, {}).get("modelle") or [] if isinstance(m, dict)]


def eigen_speichern(m, path=EIGENE, kat=None):
    """Adds an own entry (checked again); refuses a second one for the same id or repository, and more than EIGENE_MAX."""
    eigen_ok(m)
    kat = katalog() if kat is None else kat
    alle = eigene(path)
    if m["id"] in kat or any(x.get("repo") == m["repo"] for x in alle) or any(x["repo"] == m["repo"] for x in kat.values()):
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
    if any(jetzt_id(a, cfg) == mid for a in TAUSCH):
        raise Fehler("aktiv")
    w = read_json(wechsel, {}).get(m.get("art")) or {}
    if w.get("alt") == mid and (time.time() if now is None else now) - float(w.get("zeit", 0)) <= ALT_TAGE * 86400:
        raise Fehler("frist")
    write_json(path, {"modelle": [x for x in alle if x.get("id") != mid]}, indent=1)
    return hf_ordner(m, hf_home)


def ordner_weg(ordner, hf_home=None):
    """Removes one model folder of the Hugging Face cache (never a link, never anything outside hub/models--*)."""
    import shutil
    hub = os.path.realpath(os.path.join(hf_home or os.environ.get("HF_HOME") or os.path.expanduser("~/.cache/huggingface"), "hub"))
    if os.path.islink(ordner) or not os.path.isdir(ordner):
        return False
    if os.path.dirname(os.path.realpath(ordner)) != hub or not os.path.basename(ordner).startswith("models--"):
        raise Fehler("ordner")
    shutil.rmtree(ordner)
    return True


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
            for a in start_args(args[1], load_config()):
                log(a)
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
        if cmd == "umzug-merken":
            merken(args[1:], load_config())
            log(f"modelle: qwen38 notiert {len(args) - 1} dienste")
            return 0
        if cmd == "umzug-vorher":
            for u in vorher()[0]:
                log(u)
            return 0
        if cmd == "umzug-schalten":
            _schreib(schalten(args[1], _roh()))
            log(f"modelle: schalter {args[1]}")
            return 0
        if cmd == "umzug-fertig":           # after the way back: the note becomes the old one, a new move may start
            if os.path.exists(VORHER):
                os.replace(VORHER, VORHER + ".alt")
            return 0
        if cmd == "rundlauf":
            import llmstart
            ok, wort = rundlauf(load_config(), log, stufe=llmstart.stufe)
            if not ok:
                llmstart.stufe("fehler", grund=wort)
            log(f"modelle: rundlauf {'ok' if ok else 'fehler ' + wort}")
            return 0 if ok else 3
        if cmd == "umzug-modell":
            m, _ = rolle("llm", load_config())
            log(f"{m['id']} {m['repo']} {m['revision'] or fest_revision(m)}")
            return 0
        if cmd == "jetzt":
            log(jetzt_id(args[1], load_config()) or "-")
            return 0
        if cmd == "wechsel-pruefen":
            # root checks again what the panel checked (the panel adds the running qwen38 lanes to the budget)
            m = wechsel_pruefen(args[1], args[2], load_config(), gesamt_gib())
            log(f"wahl {m['wahl']}" if args[1] in INSTALL else f"vllm {m['repo']} {fest_revision(m)}")
            return 0
        if cmd == "wechsel-schalten":
            if args[1] not in ROLLEN:
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
