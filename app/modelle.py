"""Modell-Katalog (plan plaene/eigene-modelle.md, Dominik 2026-10-14 „1a 2a 3a 4a 5a 6a“): the models this
installation runs itself, one line each in modelle.json, read only here.

Stage E0 measures before anything switches: `sudo speech-spark modelle messen [llm] [sehen] [fp8] [gemma]` stops the
qwen38 lanes for a while (with a Wartungspause), starts one catalog model at a time natively with vLLM on
127.0.0.1:MESS_PORT and measures it with fixed German questions, one tool call and fixed test pictures, then
starts qwen38 again. The result goes to STATE/modelle-messung.json and into the journal ("modelle:" lines with
fixed words and numbers, never an answer's text). Nothing is switched by a measurement and nothing is deleted.

Rules for every entry (test_modelle): the engine is one we know, the repository a plain "owner/name", the revision
a full commit or empty (empty only to measure), the memory share at most ANTEIL_MAX (above ~0.80 the GB10 freezes),
never trust_remote_code, only the flags vllm_args builds from the fields in VLLM_KEYS. Downloads take only the
file kinds in ERLAUBT (no pickle, no Python code) and pruefen() checks every file against its name in the
Hugging Face cache (SHA-256 for large files, the git blob hash for small ones).

Command line (as the panel's service user, from speech-spark.sh): liste · feld <id> repo|revision · messliste <was …> · vorbereiten <id> ·
pruefen <id> [revision] · vllm-args <id> [--port N] [--revision R] [--ohne-mtp] · messen-lauf <id> [--port N]
[--einheit unit] [--revision R] · ergebnis · venv <id>|llm|sehen · start-args llm|sehen (engine.sh).

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
         "bild": ("Bilder malen", "Painting pictures"), "klein": ("Kleine Modelle (CPU)", "Small models (CPU)")}
# vllm: an engine this installation starts itself (the strict rules below); the others are run as before by their
# own services and are listed for the budget: extern (qwen38), the speech models, sd.cpp, ONNX on the CPU
ENGINES = ("vllm", "extern", "qwen-asr", "qwen-tts", "sdcpp", "onnx-cpu")
BETRIEB = ("resident", "bei_bedarf")
MESSEN = ("immer", "auf_wunsch")
ANTEIL_MAX = 0.80
MESS_PORT = 31016
VLLM_KEYS = ("reasoning_parser", "tool_call_parser", "mtp", "max_seqs", "quantization", "bilder_pro_frage", "kv_cache_dtype",
             "venv")
VENVS = ("llm", "kolibri")       # $PREFIX/venv-<name>: venv-llm (install.sh --llm), venv-kolibri (install.sh --kolibri)
KV = ("fp8",)
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
QUANT = ("fp8",)
CHAT = "/v1/chat/completions"   # the engine itself on its measuring port, never the panel's model (llm.py)
GESUND_S = 1200                  # an engine has this long to load (first start compiles kernels)
# the first start compiles CUDA kernels for the GB10 (FlashInfer, torch); unbounded it runs one compiler (cicc, about
# 6 GB each) per CPU core at once and fills the unified memory (Dominik 2026-10-15: OOM kill of cicc while measuring).
# The engine units and the measurement take these; the compiled kernels stay in the cache under HOME, so it is once.
KOMPILIEREN = {"MAX_JOBS": "4", "NVCC_THREADS": "1", "TORCHINDUCTOR_COMPILE_THREADS": "4"}

# fixed German questions (TTFT and tokens per second), one tool call, two test pictures
FRAGEN = ("Erkläre in vier Sätzen, warum der Himmel blau ist.",
          "Schreib eine kurze, freundliche Mail an einen Nachbarn: Das Paket liegt bei mir, er kann es heute ab 18 Uhr holen.",
          "Fasse zusammen, was man beim Kauf eines gebrauchten Fahrrads prüfen sollte. Höchstens sechs Punkte.")
LANG = "Erzähl ausführlich, wie ein Leuchtturm funktioniert, von der Lampe bis zur Kennung. Etwa 300 Wörter."
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
    if m["engine"] == "sdcpp" and not isinstance(m.get("variante"), str):
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
    k = m.get("kontext")
    if isinstance(k, bool) or not isinstance(k, int) or not 2048 <= k <= 262144:
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


def _aus_bildmodell(m):
    """A picture entry (engine sdcpp) takes name, licence, memory, repository and disk size from bildmodell.VARIANTS:
    the files with their checksums live there, and install.sh hands that file alone to the service user."""
    if m.get("engine") != "sdcpp":
        return m
    import bildmodell
    v = bildmodell.VARIANTS.get(m.get("variante"))
    if v is None:
        raise Fehler("variante")
    return dict(m, name={"de": v["name"], "en": v["name"]}, lizenz=v["license"], gewerblich=v["commercial"],
                need_gib=v["need_gib"], repo=v["model"].repo, revision=v["model"].revision,
                platte_gb=bildmodell.disk_gb(m["variante"]))


def katalog(path=KATALOG):
    """{id: entry} from modelle.json; every entry checked, ids unique."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for m in data.get("modelle", []):
        m = _aus_bildmodell(m)
        pruefe_eintrag(m)
        if m["id"] in out:
            raise Fehler("doppelt")
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
    if chat.get("doc_semantic"):
        add(kat.get("e5-small"))
    if chat.get("rerank"):
        add(zur_variante("klein", chat.get("rerank_model"), kat) or zur_variante("klein", "klein", kat))
    return out


SYSTEM_GIB = 6     # DGX OS, the panel and the small services next to the models (plan: Speicher-Budget)


def budget(cfg, total_gib, lanes=(), kat=None):
    """The memory budget (plan „Speicher-Budget“): fixed = the resident models + system + reserve; on demand = the
    models loaded when needed. "alle" when all of them fit at once, "ein_platz" when only one on-demand model fits
    beside the fixed ones (they then run one after the other through vorrang), "zu_knapp" when not even that fits.
    A fixed rule from numbers; the model decides nothing."""
    teile = aktiv(cfg, total_gib, lanes, kat)
    reserve = float(cfg.get("memory", {}).get("reserve_gib", 10))
    fest = round(sum(x["gib"] for x in teile if x["betrieb"] == "resident"), 1)
    bedarf = [x["gib"] for x in teile if x["betrieb"] == "bei_bedarf"]
    frei = round(total_gib - SYSTEM_GIB - reserve - fest, 1)
    if frei >= sum(bedarf):
        regel = "alle"
    elif frei >= max(bedarf, default=0):
        regel = "ein_platz"
    else:
        regel = "zu_knapp"
    return {"gesamt": round(total_gib, 1), "system": SYSTEM_GIB, "reserve": reserve, "fest": fest,
            "bedarf": round(sum(bedarf), 1), "bedarf_max": round(max(bedarf, default=0), 1), "frei": frei,
            "regel": regel, "teile": teile}


def wahl(art, kat=None):
    """The entries install.sh offers for a kind, in catalog order (field "wahl" = the install's short key)."""
    if art not in ("asr", "tts", "bild"):
        raise Fehler("art")
    kat = katalog() if kat is None else kat
    return [m for m in kat.values() if m["art"] == art and m.get("wahl")]


def wahl_zeilen(art, kat=None):
    """The numbered lines of install.sh's question for one kind (English, like the install)."""
    out = []
    for i, m in enumerate(wahl(art, kat), 1):
        text = (m.get("text") or {}).get("en", "")
        if art == "bild":
            extra = "" if m["gewerblich"] else " (private use only)"
            extra += f" ({text})" if text and text != "private use only" else ""
            out.append(f"  {i}) {m['name']['en']:<24} ~{m['platte_gb']:g} GB disk, ~{m['need_gib']:g} GiB while painting, "
                       f"{m['lizenz']}{extra}")
        else:
            out.append(f"  {i}) {m['name']['en']:<26} {text + ', ' if text else ''}~{m['need_gib']:g} GiB")
    return out


def messliste(was, kat=None):
    """The ids to measure, in catalog order: was = words llm, sehen (the entries marked "immer"), fp8, gemma
    (one entry each that is measured only on request); no word means llm and sehen."""
    kat = katalog() if kat is None else kat
    was = list(was) or ["llm", "sehen"]
    wunsch = {"fp8": "qwen38-27b-fp8", "gemma": "gemma-4-26b-a4b", "kolibri": "kolibri-1-nvfp4"}
    if any(w not in ("llm", "sehen") and w not in wunsch for w in was):
        raise Fehler("was")
    ids = [w for w in (wunsch.get(x) for x in was) if w]
    return [i for i, m in kat.items() if m["engine"] == "vllm" and (i in ids or (m["art"] in was and m["messen"] == "immer"))]


def vllm_args(m, port=MESS_PORT, revision="", mtp=True):
    """The arguments after `vllm serve`: only from the catalog's checked fields, never trust_remote_code, always
    on 127.0.0.1. revision may stand in only for an entry without one (a measurement after the download)."""
    pruefe_eintrag(m)
    if m["engine"] != "vllm":
        raise Fehler("engine")
    rev = m["revision"] or revision
    if not REV.match(rev or "") or (m["revision"] and revision and revision != m["revision"]):
        raise Fehler("revision")
    if isinstance(port, bool) or not isinstance(port, int) or not 31000 <= port <= 31099:
        raise Fehler("port")
    v = m["vllm"]
    a = [m["repo"], "--revision", rev, "--host", "127.0.0.1", "--port", str(port),
         "--served-model-name", m["id"], "--max-model-len", str(m["kontext"]),
         "--gpu-memory-utilization", f"{m['anteil']:.2f}", "--max-num-seqs", str(v.get("max_seqs", 8)),
         "--generation-config", "vllm", "--no-enable-flashinfer-autotune",
         "--disable-uvicorn-access-log"]   # stats stay on: /metrics counts the MTP hits
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
    return a


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
    return m, port


def start_args(art, cfg, messung=None, kat=None, hf_home=None):
    """The arguments after `vllm serve` for speech-spark-llm / speech-spark-sehen (engine.sh llm|sehen): the
    pinned commit, its files checked (kinds and links; the hashes were checked at the download), offline."""
    m, port = rolle(art, cfg, kat)
    rev = fest_revision(m, messung)
    pruefen(hf_ordner(m, hf_home), rev, hashes=False)
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


def vorbereiten(m, hf_home=None):
    """Makes sure the weights are in the cache (download only the ERLAUBT kinds) and checks them. Returns the
    commit. A pinned revision is fetched exactly; an empty one takes the newest commit (only to measure)."""
    ordner = hf_ordner(m, hf_home)
    rev = m["revision"]
    if rev:
        try:
            pruefen(ordner, rev)
            return rev
        except Fehler:
            pass
    from huggingface_hub import snapshot_download
    path = snapshot_download(m["repo"], revision=rev or None, allow_patterns=list(ERLAUBT))
    commit = os.path.basename(os.path.normpath(path))
    if rev and commit != rev:
        raise Fehler("revision")
    pruefen(ordner, commit)
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


def stream_messen(port, body, timeout=300, now=time.monotonic):
    """One streamed answer: (seconds to the first token, tokens, tokens per second after the first)."""
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
    end = now()
    if first is None:
        raise Fehler("leer")
    return round(first - t0, 2), tokens, round(tokens / max(end - first, 1e-3), 1)


def spec_zaehler(text):
    """(accepted, drafted) speculative tokens from vLLM's /metrics text, 0 when absent."""
    def summe(name):
        return sum(float(x) for x in re.findall(rf"^vllm:{name}(?:{{[^}}]*}})? ([0-9.e+]+)$", text, re.M))
    return summe("spec_decode_num_accepted_tokens_total"), summe("spec_decode_num_draft_tokens_total")


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


class Speicher(threading.Thread):
    """Samples MemAvailable every half second; tiefst = the lowest value seen."""
    def __init__(self):
        super().__init__(daemon=True)
        self.tiefst = mem_available_gib()
        self.halt = threading.Event()

    def run(self):
        while not self.halt.wait(0.5):
            self.tiefst = min(self.tiefst, mem_available_gib())


def _aktiv(einheit):
    if not einheit:
        return True
    r = subprocess.run(["systemctl", "is-active", einheit], capture_output=True, text=True)
    return r.stdout.strip() in ("active", "activating")


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
         "frei_start_gib": round(frei_start, 1)}
    try:
        r["laden_s"] = warte_bereit(m, port, einheit)
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
        if m["art"] == "llm" and cfg.get("image", {}).get("enabled"):
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
    if "mtp_annahme" in r:
        teile.append(f"mtp {int(r['mtp_annahme'] * 100)} %")
    if "mtp" in r:
        teile.append("mtp " + r["mtp"])
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
    return f"http://127.0.0.1:{int(cfg.get('llm', {}).get('port', 31006))}/v1"


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


def rundlauf(cfg, log=print, frist=GESUND_S, now=time.monotonic, sleep=time.sleep):
    """The check before the chat switches: through the door with the API key a German sentence, a tool call, a picture
    (when the model or the image understanding model can see) and one System One question. Returns (ok, word)."""
    c = cfg.get("llm", {})
    port, key = int(c.get("port", 31006)), str(cfg.get("api", {}).get("key") or "")
    m, _ = rolle("llm", cfg)
    t0 = now()
    while True:
        try:
            if json.loads(_get(port, "/health")).get("status") == "ready":
                break
        except Exception:
            pass
        if now() - t0 > frist:
            return False, "nicht bereit"
        sleep(5)
    log(f"modelle: rundlauf bereit nach {int(now() - t0)} s")
    try:
        satz = _text(_post(port, CHAT, {"messages": [{"role": "user", "content": FRAGEN[0]}], "max_tokens": 200}, key=key))
        if len(re.findall(r"[a-zäöüß]{3,}", satz.lower())) < 5:
            return False, "satz"
        log("modelle: rundlauf satz ok")
        if m["werkzeuge"] and not werkzeug_ok(_post(port, CHAT, {"messages": [{"role": "user", "content": WERKZEUG_FRAGE}],
                                                                 "max_tokens": 200, "tools": [WERKZEUG], "tool_choice": "auto"},
                                                         key=key)):
            return False, "werkzeug"
        log("modelle: rundlauf werkzeug ok")
        if m["kann_sehen"] or c.get("sehen_modell"):
            text_url, _ = testbilder()
            if not bild_text_ok(_text(_post(port, CHAT, dict(_bild_frage(m, text_url, BILD_TEXT_FRAGE)), key=key))):
                return False, "bild"
            log("modelle: rundlauf bild ok")
        so = _post(port, "/v1/systemone", {"state": "Wie wird das Wetter morgen in Hamburg?", "questions": {
            "wetter": {"type": "noul", "instructions": "Fragt der Text nach dem Wetter?"}}}, key=key, timeout=60)
        p = (so.get("answers") or {}).get("wetter", {}).get("noul")
        if not isinstance(p, (int, float)) or p < 0.5:
            return False, "systemone"
        log("modelle: rundlauf systemone ok")
    except Exception as e:
        return False, type(e).__name__.lower()[:24]
    return True, "ok"


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
            if args[2] not in ("repo", "revision"):
                raise Fehler("feld")
            log(m[args[2]])
            return 0
        if cmd == "messliste":
            log(" ".join(messliste(args[1:])))
            return 0
        if cmd == "vllm-args":
            for a in vllm_args(eintrag(args[1]), int(_opt(args, "--port", MESS_PORT)), _opt(args, "--revision"),
                               mtp="--ohne-mtp" not in args):
                log(a)
            return 0
        if cmd == "vorbereiten":
            m = eintrag(args[1])
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
            ok, wort = rundlauf(load_config(), log)
            log(f"modelle: rundlauf {'ok' if ok else 'fehler ' + wort}")
            return 0 if ok else 3
        if cmd == "umzug-modell":
            m, _ = rolle("llm", load_config())
            log(f"{m['id']} {m['repo']} {m['revision'] or fest_revision(m)}")
            return 0
        if cmd == "ergebnis":
            data = read_json(MESSUNG, {})
            for mid, r in (data.get("modelle") or {}).items():
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
