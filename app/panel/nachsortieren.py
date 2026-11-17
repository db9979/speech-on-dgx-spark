"""Treffer nachsortieren (plan plaene/suche-schaerfen.md, Stufe 3): a cross-encoder reads the question and each of
the mixed search's candidates together and gives a score; the best come first, the ones below a fixed floor go.

- Admin switch Funktionen → Eigene Dokumente → "Treffer nachsortieren" (chat.rerank, off; no profile switch, never
  guests), the model chat.rerank_model ("klein": multilingual MiniLM from mMARCO, about 120 MB; "gross":
  bge-reranker-v2-m3, about 570 MB) and the time budget chat.rerank_ms (300 to 2000, default 800).
- The model runs on the CPU in its own low-priority process (embed_worker.py rank …), never on the GPU, only with
  MIN_FREE_GIB free memory, and ends after IDLE_STOP seconds without work. Its files come once from Hugging Face;
  their SHA-256 is pinned in state/doc-rank.json the first time and other files are refused later.
- A search never waits for the model to start (the start runs on its own, this search keeps the mixed order),
  never longer than the budget (the answer is then dropped when it comes), and never while another re-ranking
  runs: in all these cases the order of the mix stays. The quick look "Erst lokal" (keep=False) only re-ranks
  while the model runs anyway.
- An own model (Dominik 2026-11-17, stage „klein via ONNX“: Zustand → Modelle, Kleine Modelle): chat.rerank_model is
  then its id, its entry (modelle.klein_vorschlag) names one .onnx file on a pinned commit and its SHA-256. At its first
  start in this process it must pass modelle.KLEIN_PROBE (the passage that answers scores higher); else it is refused
  until the panel restarts and the small checked one works instead (back to the model before).
- The journal gets fixed words and numbers only (never the question or a passage), Logs → Anfragen a step
  "Nachsortieren" with the numbers, the Live page the model while it works.
"""
import asyncio
import json
import os
import sys
import time

import features
from common import STATE, load_config, write_json
import modelle

PINS = os.path.join(STATE, "doc-rank.json")
WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "embed_worker.py")
SIZES = {"klein": ("klein", "small"), "gross": ("groß", "large")}
NEED_GIB = {v: modelle.zur_variante("klein", v)["need_gib"] for v in SIZES}   # from the model catalog
_abgelehnt = set()             # own models that failed the probe in this process
IDLE_STOP = 600
START_TIMEOUT = 600            # the first start downloads the model
CANDIDATES = 30                # what the mix hands over (documents.search's own depth)
MAX_CHARS = 1500               # of a passage the model reads (with its context line)
MIN_SCORE = -4.0               # below this (about 2 % as a probability) a passage does not answer the question

_proc = None
_size = None
_last = [0.0]
_lock = None
_start_task = None
_status = {"state": "off", "error": "", "ms": 0, "at": 0}


def _chat(c=None):
    return (c or load_config()).get("chat", {})


def admin_on(c=None):
    return features.admin_on("nachsortieren", c)


def size(c=None):
    """The model to use: klein, gross or an own one of the catalog that has not failed its probe."""
    s = _chat(c).get("rerank_model", "klein")
    if s in SIZES:
        return s
    if isinstance(s, str) and s.startswith("eigen-") and s not in _abgelehnt and _eigen(s):
        return s
    return "klein"


def _eigen(s):
    m = modelle.zur_variante("klein", s)
    return m if m and m.get("eigen") else None


def need_gib(sz):
    return NEED_GIB.get(sz) or (_eigen(sz) or {}).get("need_gib") or max(NEED_GIB.values())


def budget_ms(c=None):
    v = _chat(c).get("rerank_ms", 800)
    return v if isinstance(v, int) and not isinstance(v, bool) and 300 <= v <= 2000 else 800


def _free_gib():
    try:
        import psutil
        return psutil.virtual_memory().available / 1024**3
    except Exception:
        return 0.0


def running():
    return bool(_proc and _proc.returncode is None)


def busy():
    return bool(_lock and _lock.locked())


def status(now=None):
    out = dict(_status, running=running(), busy=busy(), size=size(), need_gib=need_gib(size()),
               stop_min=IDLE_STOP // 60, budget=budget_ms())
    if running():
        out["stop_in"] = max(0, int(IDLE_STOP - ((now or time.time()) - _last[0])))
        try:
            import psutil
            out["mib"] = round(psutil.Process(_proc.pid).memory_info().rss / 1024**2)
        except Exception:
            pass
    return out


def _pins():
    try:
        with open(PINS) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _check_pins(sz, sha, commit):
    """True if these model files are the ones first seen for this size and commit (recorded the first time). A new
    commit in the catalog records its files anew: the catalog pins it and the worker checked every file against its
    name (a pin from before the commits were pinned, or of the other file, would refuse the model forever)."""
    if not isinstance(sha, dict) or not sha or not all(isinstance(v, str) for v in sha.values()):
        return False
    pins = _pins()
    alt = pins.get(sz)
    if isinstance(alt, dict) and alt.get("commit") == commit:
        return alt.get("sha") == sha
    pins[sz] = {"commit": commit, "sha": sha}
    write_json(PINS, pins, mode=0o644)
    if alt:
        print("wissen: nachsortieren modell neuer stand", flush=True)
    return True


def _stop():
    global _proc, _size
    if _proc and _proc.returncode is None:
        try:
            _proc.kill()
        except ProcessLookupError:
            pass
    _proc, _size = None, None
    if _status["state"] in ("ready", "starting"):
        _status["state"] = "off"


def idle_stop(now=None):
    """Ends the model after IDLE_STOP seconds without work, or when the admin switched it off or to the other size."""
    if not running() or busy():
        return
    if not admin_on() or _size != size() or (now or time.time()) - _last[0] > IDLE_STOP:
        _stop()
        print("wissen: nachsortieren modell gestoppt", flush=True)


async def _start():
    global _proc, _size
    sz = size()
    if _free_gib() < need_gib(sz):
        _status.update(state="waiting", error="zu wenig freier Arbeitsspeicher")
        print("wissen: nachsortieren modell wartet | arbeitsspeicher", flush=True)
        return
    _status.update(state="starting", error="")
    m = modelle.zur_variante("klein", sz)    # its repository and pinned commit (the worker checks every file)
    if not m:
        _status.update(state="error", error="Modell nicht im Katalog")
        print("wissen: nachsortieren modell fehler | katalog", flush=True)
        return
    eigen = bool(m.get("eigen"))      # an own one: the worker loads its named file and checks it against the commit
    args = ["rank", "eigen", m["repo"], m["revision"], m["datei"]["path"]] if eigen else ["rank", sz, m["repo"], m["revision"]]
    _proc = await asyncio.create_subprocess_exec(sys.executable, "-I", WORKER, *args,
                                                 stdin=asyncio.subprocess.PIPE,
                                                 stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                                                 limit=4 * 1024**2)
    _size = sz
    try:
        hello = json.loads(await asyncio.wait_for(_proc.stdout.readline(), START_TIMEOUT) or b"{}")
        if not hello.get("ready"):
            raise RuntimeError("did not start")
        # the commit is the catalog's (modelle.json), never the worker's; a worker that checked another one is refused
        if eigen and (hello.get("sha") or {}).get(f"{m['repo']}/{m['datei']['path']}") != m["datei"]["sha256"]:
            raise RuntimeError("model files changed")      # an own file: the SHA-256 its entry was added with
        if hello.get("commit") != m["revision"] or not _check_pins(sz, hello.get("sha"), m["revision"]):
            raise RuntimeError("model files changed")
        if eigen:
            q, texts = modelle.KLEIN_PROBE
            ok, wort = modelle.klein_probe(await _probe_scores(q, list(texts)))
            print(f"wissen: nachsortieren probe {'ok' if ok else 'fehler'} | {wort}", flush=True)
            if not ok:
                _abgelehnt.add(sz)
                raise RuntimeError("probe")
    except BaseException as e:
        _stop()
        why = str(e) if isinstance(e, RuntimeError) else type(e).__name__
        _status.update(state="error", error={"did not start": "Modell startet nicht (Download oder Datei fehlt)",
                                             "model files changed": "Modelldateien anders als beim ersten Mal für diesen Stand (state/doc-rank.json)",
                                             "probe": "Eigenes Modell hat die Probe nicht bestanden, das kleine geprüfte arbeitet weiter"}.get(why, why))
        print(f"wissen: nachsortieren modell fehler | {why if why in ('did not start', 'model files changed', 'probe') else 'start'}", flush=True)
        return
    _last[0] = time.time()
    _status.update(state="ready", error="")
    print(f"wissen: nachsortieren modell bereit | {sz}", flush=True)


def _wake():
    """Starts the model on its own; the search that asked keeps the mixed order."""
    global _start_task
    if _start_task and not _start_task.done():
        return
    _start_task = asyncio.get_running_loop().create_task(_start())


async def _probe_scores(query, texts):
    """The probe's scores, holding the lock so no search writes to the worker meanwhile; None when it does not answer."""
    global _lock
    if _lock is None or getattr(_lock, "_loop", None) not in (None, asyncio.get_running_loop()):
        _lock = asyncio.Lock()
    async with _lock:
        try:
            return await asyncio.wait_for(_scores(query, texts), 60)
        except (RuntimeError, ValueError, asyncio.TimeoutError):
            return None


async def _scores(query, texts):
    _proc.stdin.write((json.dumps({"query": query, "texts": texts}) + "\n").encode())
    await _proc.stdin.drain()
    d = json.loads(await _proc.stdout.readline() or b"{}")
    if not isinstance(d.get("scores"), list) or len(d["scores"]) != len(texts):
        raise RuntimeError("no answer")
    return [float(x) for x in d["scores"]]


async def _held(query, texts):
    try:
        t0 = time.time()
        out = await _scores(query, texts)
        import verbrauch   # Verbrauchszähler: pairs of question and hit the cross-encoder scored
        verbrauch.add("rerank", "Treffer nachsortieren", amount=len(texts), ms=int((time.time() - t0) * 1000))
        return out
    except BaseException:
        _stop()    # an answer left in the pipe would belong to the next question
        raise
    finally:
        _last[0] = time.time()
        _lock.release()


def _text(h):
    return ((h.get("head") or "") + "\n" + str(h.get("text") or ""))[:MAX_CHARS].strip()


async def rank(query, hits, k=5, keep=True, trace=None):
    """hits in the cross-encoder's order, the ones below MIN_SCORE left out, the first k; or (when the model sleeps,
    starts, is busy, slow or broken) the mix's order. Returns (hits, word) with word one of: ok, aus, startet,
    belegt, langsam, fehler, leer."""
    global _lock
    t0 = time.time()
    query = str(query or "").strip()
    if not hits or not query:
        return hits[:k], "leer"
    if _lock is None or getattr(_lock, "_loop", None) not in (None, asyncio.get_running_loop()):
        _lock = asyncio.Lock()
    word, out, n_in = "ok", hits[:k], len(hits[:CANDIDATES])
    if not running() or _size != size():
        if keep:
            if running():
                _stop()
            _wake()
        word = "startet" if keep else "aus"
    elif _lock.locked():
        word = "belegt"
    else:
        await _lock.acquire()
        cands = hits[:CANDIDATES]
        task = asyncio.ensure_future(_held(query, [_text(h) for h in cands]))
        try:
            scores = await asyncio.wait_for(asyncio.shield(task), budget_ms() / 1000)
            order = sorted(range(len(cands)), key=lambda i: -scores[i])
            out = [dict(cands[i], rank=round(scores[i], 3)) for i in order if scores[i] >= MIN_SCORE][:k]
        except asyncio.TimeoutError:
            word = "langsam"      # the answer is dropped when it comes; the lock is freed then
        except Exception:
            word = "fehler"
    ms = int((time.time() - t0) * 1000)
    if word == "ok":
        _status.update(ms=ms, at=int(time.time()))
        print(f"wissen: nachsortieren | {n_in} -> {len(out)} | {ms} ms", flush=True)
    else:
        print(f"wissen: nachsortieren {word} | {n_in} treffer | reihenfolge der mischung", flush=True)
    if trace is not None:
        try:
            trace.step("tool", "Nachsortieren", t0, time.time(), n=n_in, keep=len(out), state=word)
        except Exception:
            pass
    return out, word

