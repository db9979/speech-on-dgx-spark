"""Meaning vectors for the document search ("Bedeutungssuche", V01.0.223).

A small embedding model (multilingual-e5-small, quantized ONNX, about 120 MB on disk and 300 MB in
memory) runs on the CPU in its own process (embed_worker.py), so nothing sits next to vLLM on the
GPU and all its memory is free again once the process ends:

- it starts only when a profile with the switch on needs vectors (new pieces, or a question), and only
  while at least MIN_FREE_GIB of memory is available; it ends after IDLE_STOP seconds without work;
- the model files come once from Hugging Face; their SHA-256 is written to state/doc-embed.json the
  first time, and a later download with other contents is refused (no silent model swap);
- a question waits at most QUERY_TIMEOUT seconds for its vector; without one the search is full-text
  only, never an error.

Tests replace embed() with their own function.
"""
import asyncio
import base64
import json
import os
import sys
import time

STATE = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
PINS = os.path.join(STATE, "doc-embed.json")
WORKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "embed_worker.py")
DIM = 384
BATCH = 16
MIN_FREE_GIB = 8.5
IDLE_STOP = 600
START_TIMEOUT = 300            # the first start downloads the model
QUERY_TIMEOUT = 8
CALL_TIMEOUT = 120

_proc = None
_last = [0.0]
_locks = {}                    # event loop -> lock (the panel has one loop; tests start several)
_status = {"state": "off", "error": ""}


def _lock():
    loop = asyncio.get_running_loop()
    if loop not in _locks:
        _locks.clear()
        _locks[loop] = asyncio.Lock()
    return _locks[loop]


def _busy():
    return any(x.locked() for x in _locks.values())


def status():
    return dict(_status, running=bool(_proc and _proc.returncode is None))


def memory_mib():
    """Working memory of the model process in MiB, None while it does not run."""
    try:
        import psutil
        return round(psutil.Process(_proc.pid).memory_info().rss / 1024**2) if _proc and _proc.returncode is None else None
    except Exception:
        return None


def _free_gib():
    try:
        import psutil
        return psutil.virtual_memory().available / 1024**3
    except Exception:
        return 0.0


def _pins():
    try:
        with open(PINS) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _check_pins(sha):
    """True if these model files are the ones first seen (they are recorded the first time)."""
    if not isinstance(sha, dict) or not all(isinstance(v, str) for v in sha.values()):
        return False
    old = _pins()
    if old:
        return old == sha
    os.makedirs(STATE, exist_ok=True)
    tmp = PINS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(sha, f)
    os.replace(tmp, PINS)
    return True


async def _start(timeout):
    global _proc
    if _proc and _proc.returncode is None:
        return
    if _free_gib() < MIN_FREE_GIB:
        _status.update(state="waiting", error="zu wenig freier Arbeitsspeicher")
        raise RuntimeError("not enough free memory for the embedding model")
    _status.update(state="starting", error="")
    _proc = await asyncio.create_subprocess_exec(sys.executable, "-I", WORKER, stdin=asyncio.subprocess.PIPE,
                                                 stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                                                 limit=4 * 1024**2)
    try:
        line = await asyncio.wait_for(_proc.stdout.readline(), timeout)
        hello = json.loads(line or b"{}")
        if not hello.get("ready"):
            raise RuntimeError(str(hello.get("error") or "the embedding model did not start")[:200])
        if not _check_pins(hello.get("sha")):
            raise RuntimeError("the model files differ from the ones first downloaded (state/doc-embed.json)")
    except BaseException as e:
        _stop()
        _status.update(state="error", error=f"{type(e).__name__}: {str(e)[:160]}")
        raise
    _status.update(state="ready", error="")
    print("docembed: embedding model ready", flush=True)


def _stop():
    global _proc
    if _proc and _proc.returncode is None:
        try:
            _proc.kill()
        except ProcessLookupError:
            pass
    _proc = None
    if _status["state"] in ("ready", "starting"):
        _status.update(state="off")


def idle_stop(now=None):
    """Ends the model process after IDLE_STOP seconds without work (memory back for the rest)."""
    if _proc and (now or time.time()) - _last[0] > IDLE_STOP and not _busy():
        _stop()
        print("docembed: embedding model stopped (idle)", flush=True)


async def _call(texts, kind, timeout):
    # a question waits only briefly for a batch of pieces in the background
    lock = _lock()
    await asyncio.wait_for(lock.acquire(), None if kind == "passage" else 3)
    try:
        _last[0] = time.time()
        await _start(START_TIMEOUT if kind == "passage" else timeout)
        try:
            _proc.stdin.write((json.dumps({"kind": kind, "texts": texts}) + "\n").encode())
            await _proc.stdin.drain()
            line = await asyncio.wait_for(_proc.stdout.readline(), timeout)
        except BaseException:
            _stop()    # an answer left in the pipe would belong to the next question
            raise
        _last[0] = time.time()
        d = json.loads(line or b"{}")
        if "vecs" not in d:
            _stop()
            raise RuntimeError(str(d.get("error") or "no answer")[:200])
        raw = base64.b64decode(d["vecs"])
        if len(raw) != len(texts) * DIM * 2:
            raise RuntimeError("unexpected vector size")
        return [raw[i * DIM * 2:(i + 1) * DIM * 2] for i in range(len(texts))]
    finally:
        lock.release()


async def embed(texts, kind):
    """float16 bytes (DIM values, length 1) per text; kind "query" or "passage"."""
    return await _call([str(t)[:2000] for t in texts][:BATCH], kind,
                       CALL_TIMEOUT if kind == "passage" else QUERY_TIMEOUT)


async def query(text):
    """The question's vector as a list of floats, or None (off, starting, too little memory, error)."""
    import numpy as np
    try:
        v = (await embed([text], "query"))[0]
        return np.frombuffer(v, dtype=np.float16).astype(float).tolist()
    except Exception as e:
        print("docembed: no vector for the question:", type(e).__name__, flush=True)
        return None
