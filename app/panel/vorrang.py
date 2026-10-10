"""Speech first: speech recognition and speech output always go before the panel's background work
(fixed rule, no switch; plan plaene/vorrang-sprache.md).

"Speech is running" = an answer streams (chat.py marks it) or the ASR / TTS services answered a
request (common.SpeechMark touches STATE/speech-active, which also counts Open WebUI, Wyoming, the
speakers and the iPhone app), and GRACE seconds after that for the follow-up question.

For background work (learning, tidying, agents, proactive notes, briefings, quality test, backup,
reading uploads ...):

    r = await vorrang.post(c, "Lernen", url, json=payload, headers=headers)   # one request to the model
    r = await vorrang.run("Lernen", lambda: c.post(...))                       # the same, any coroutine
    await vorrang.quiet("Sicherung")                                            # only wait for a pause
    x = await vorrang.in_thread("Suchindex", fn, arg)                           # CPU work, low priority
    vorrang.hold("Mail sortieren")                                              # inside a worker thread

run()/post() wait for a pause, let only one background request run at a time and cancel it as soon
as somebody speaks (vLLM stops the request when the connection closes, so the GPU is free at once);
it starts again in the next pause, at most RETRIES times, then Busy is raised. Journal lines start
with "vorrang:".
"""
import asyncio
import os
import threading
import time

from common import SPEECH_MARK, speech_mark

GRACE = 20          # seconds after the last speech that still count as "speaking" (follow-up question)
POLL = 0.25         # how often a running background request checks for speech
RETRIES = 3         # a background request cancelled this often gives up until its next turn
LOW_NICE = 15       # CPU priority of background threads (in_thread)
MARK = SPEECH_MARK

_local = [0.0]      # this process: the last time an answer streamed
_sem = {}           # event loop -> Semaphore(1): one background request at a time
stats = {}          # per day: held, waited_max, cancelled, gave_up, behind


class Busy(Exception):
    """Background work given up because speech kept interrupting it."""


def last_speech():
    try:
        t = os.path.getmtime(MARK)
    except OSError:
        t = 0.0
    return max(_local[0], t)


def speaking(now=None):
    now = time.time() if now is None else now
    return now - last_speech() < GRACE


def mark(now=None, end=False):
    """The panel itself is talking (an answer streams): also tells other processes."""
    now = time.time() if now is None else now
    _local[0] = max(_local[0], now)
    speech_mark(now, MARK, end=end)


def _day(now=None):
    t = time.localtime(time.time() if now is None else now)
    d = f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"
    if d not in stats:
        stats.clear()
        stats[d] = {"held": 0, "waited_max": 0, "cancelled": 0, "gave_up": 0, "behind": 0}
    return stats[d]


def count(key, now=None, value=1):
    s = _day(now)
    if key == "waited_max":
        s[key] = max(s[key], int(value))
    else:
        s[key] += value


def today(now=None):
    return dict(_day(now), speaking=speaking(now))


async def quiet(job, sleep=asyncio.sleep):
    """Waits until nobody speaks. Returns the seconds waited."""
    if not speaking():
        return 0
    t0 = time.time()
    count("held")
    print(f"vorrang: {job} wartet (Gespräch)", flush=True)
    while speaking():
        await sleep(1)
    waited = time.time() - t0
    count("waited_max", value=waited)
    print(f"vorrang: {job} wartete {waited:.0f} s", flush=True)
    return waited


def hold(job, sleep=time.sleep):
    """quiet() for code in a worker thread (never call it on the event loop)."""
    if not speaking():
        return 0
    t0 = time.time()
    count("held")
    print(f"vorrang: {job} wartet (Gespräch)", flush=True)
    while speaking():
        sleep(1)
    waited = time.time() - t0
    count("waited_max", value=waited)
    print(f"vorrang: {job} wartete {waited:.0f} s", flush=True)
    return waited


def _slot():
    loop = asyncio.get_running_loop()
    if loop not in _sem:
        _sem.clear()            # an old loop (tests) is gone
        _sem[loop] = asyncio.Semaphore(1)
    return _sem[loop]


async def run(job, factory, retries=RETRIES, sleep=asyncio.sleep):
    """Runs factory() (a function returning a fresh coroutine) as background work, see above."""
    async with _slot():
        for _ in range(retries + 1):
            await quiet(job, sleep)
            task = asyncio.ensure_future(factory())
            while not task.done():
                await asyncio.wait({task}, timeout=POLL)
                if not task.done() and speaking():
                    task.cancel()
                    try:
                        await task
                    except BaseException:
                        pass
                    count("cancelled")
                    print(f"vorrang: {job} abgebrochen (Gespräch), läuft in der nächsten Pause neu", flush=True)
                    break
            else:
                return task.result()
        count("gave_up")
        print(f"vorrang: {job} aufgegeben nach {retries + 1} Abbrüchen", flush=True)
        raise Busy(job)


async def post(c, job, url, **kw):
    """One background request to the language model (httpx client c), see run()."""
    return await run(job, lambda: c.post(url, **kw))


async def in_thread(job, fn, *args):
    """Waits for a pause, then runs fn(*args) in its own thread with low CPU priority (nice LOW_NICE).
    Long work should call hold(job) between its steps."""
    await quiet(job)
    loop = asyncio.get_running_loop()
    fut = loop.create_future()

    def done(value, err):
        if fut.done():
            return
        if err is not None:
            fut.set_exception(err)
        else:
            fut.set_result(value)

    def work():
        try:   # only this thread: a raised nice value cannot be taken back without root
            os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), LOW_NICE)
        except (OSError, AttributeError):
            pass
        try:
            value, err = fn(*args), None
        except BaseException as e:
            value, err = None, e
        loop.call_soon_threadsafe(done, value, err)
    threading.Thread(target=work, name=f"bg-{job}", daemon=True).start()
    return await fut


# ---------------------------------------------------------------- measuring (Zustand → Prüfen)
TEST_TEXT = ("Guten Abend. Das ist ein kurzer Test, ob die Sprachausgabe flüssig bleibt, während im "
             "Hintergrund gearbeitet wird. Danach schreibt die Spracherkennung den Satz wieder auf.")
LOAD_PROMPT = "Erzähl eine lange, ruhige Geschichte über einen Leuchtturm an der Nordsee, mindestens 800 Wörter."
LOAD_TOKENS = 1500
_test = {"running": False, "result": None}


def _wav(pcm, rate=24000):
    import struct
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + struct.pack("<I", len(pcm)) + pcm)


async def _speak(c, cfg, headers):
    """One TTS request like an answer sentence: (first audio s, real-time factor, pcm or wav)."""
    import base64
    import json
    url = f"http://127.0.0.1:{cfg['tts']['port']}/v1/audio/speech"
    t0 = time.time()
    if cfg["tts"].get("backend") != "vllm-omni":   # the old backend does not stream
        r = await c.post(url, headers=headers, json={"input": TEST_TEXT, "language": "German", "response_format": "wav"})
        r.raise_for_status()
        total = time.time() - t0
        secs = max(len(r.content) - 44, 0) / 48000
        return None, (total / secs if secs else None), r.content
    first, pcm = None, b""
    async with c.stream("POST", url, headers=headers, json={"input": TEST_TEXT, "language": "German", "stream": True,
                                                            "response_format": "pcm"}) as r:
        if r.status_code != 200:
            raise RuntimeError(f"TTS HTTP {r.status_code}")
        buf = b""
        async for chunk in r.aiter_raw():
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if line.startswith(b"data:") and b"speech.audio.delta" in line:
                    piece = base64.b64decode(json.loads(line[5:])["audio"])
                    if piece and first is None:
                        first = time.time() - t0
                    pcm += piece
    secs = len(pcm) / 48000
    return first, ((time.time() - t0) / secs if secs else None), _wav(pcm)


async def _hear(c, cfg, headers, wav):
    if not wav or not cfg["asr"].get("enabled", True):
        return None
    t0 = time.time()
    r = await c.post(f"http://127.0.0.1:{cfg['asr']['port']}/v1/audio/transcriptions", headers=headers,
                     files={"file": ("vorrang.wav", wav)}, data={"language": "German"})
    r.raise_for_status()
    return time.time() - t0


async def _load(c, ccfg, headers, model, started):
    """A long answer of the language model, as background work would ask for it."""
    payload = {"model": model, "max_tokens": LOAD_TOKENS, "temperature": 0.7, "stream": True,
               "chat_template_kwargs": {"enable_thinking": False},
               "messages": [{"role": "user", "content": LOAD_PROMPT}]}
    async with c.stream("POST", ccfg["llm_url"].rstrip("/") + "/chat/completions", json=payload, headers=headers) as r:
        r.raise_for_status()
        async for _ in r.aiter_lines():
            started.set()
    return True


def _r(x, n=2):
    return None if x is None else round(x, n)


def verdict(res):
    """Fixed rules: does background work slow speech down, and does the priority rule help?"""
    a, b, v = res.get("alone") or {}, res.get("load") or {}, res.get("vorrang") or {}

    def slower(x):
        if not x or not a:
            return False
        fa, fx = a.get("first") or 0, x.get("first") or 0
        ra, rx = a.get("rtf") or 0, x.get("rtf") or 0
        return fx > fa * 1.3 + 0.3 or rx > ra * 1.2 + 0.05
    if not b:
        return {"level": "warn", "title": t2("Ohne Sprachmodell nur der Wert alleine gemessen.",
                                              "Measured alone only, no language model.")}
    if not slower(b):
        return {"level": "ok", "title": t2("Hintergrundarbeit bremst die Sprache hier kaum.",
                                            "Background work hardly slows speech down here.")}
    if not slower(v):
        return {"level": "ok", "title": t2("Hintergrundarbeit bremst die Sprache, die Vorfahrt gleicht das aus.",
                                            "Background work slows speech down, the priority rule makes up for it.")}
    return {"level": "bad", "title": t2("Auch mit Vorfahrt ist die Sprache langsamer. Bitte das Ergebnis in den Thread geben.",
                                         "Speech is slower even with the priority rule. Please send the result to the thread.")}


def t2(de, en):
    return {"de": de, "en": en}


async def _people(c, cfg, h):
    """Case "Zwei Personen gleichzeitig" (priority for people, stufe.py): the TTS is full with sentences of
    others (as many as it takes at once plus two waiting), then one more sentence comes, once as a normal
    profile and once with Vorrang. With Vorrang it skips the waiting ones and only waits for a free slot."""
    import stufe
    n = cfg["tts"].get("engine_max_seqs", 2)
    n = (n if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= 8 else 2) + 2
    out = {"load": n}
    for name, extra in (("normal", {}), ("vorrang", stufe.headers("vorrang"))):
        loads = [asyncio.ensure_future(_speak(c, cfg, h)) for _ in range(n)]
        try:
            await asyncio.sleep(0.5)        # the others are in the TTS first
            first, rtf, _ = await _speak(c, cfg, dict(h, **extra))
            out[name] = {"first": _r(first), "rtf": _r(rtf)}
        finally:
            for task in loads:
                task.cancel()
            for task in loads:
                try:
                    await task
                except BaseException:
                    pass
        await asyncio.sleep(1)
    return out


def people_verdict(p):
    a, b = (p or {}).get("normal") or {}, (p or {}).get("vorrang") or {}
    if a.get("first") is None or b.get("first") is None:
        return None
    if b["first"] <= a["first"] * 0.8:
        d = round(a["first"] - b["first"], 1)
        return {"level": "ok", "title": t2(f"Mit Vorrang kommt der erste Ton {d} s früher, wenn mehrere gleichzeitig reden.",
                                            f"With priority the first audio comes {d} s sooner when several people talk at once.")}
    return {"level": "warn", "title": t2("Kaum Unterschied: Die Sprachausgabe staut sich hier wenig.",
                                          "Hardly a difference: speech output hardly queues here.")}


async def measure(sleep=asyncio.sleep):
    """Zustand → Prüfen → "Vorrang prüfen": a sentence spoken and heard (a) alone, (b) while a long
    background answer of the language model runs without the rule, (c) the same with the rule."""
    import httpx
    import chat
    from common import load_config
    from core import api_headers
    cfg = load_config()
    ccfg = cfg.get("chat", {})
    h = api_headers()
    res = {"t": int(time.time()), "alone": None, "load": None, "vorrang": None, "error": ""}
    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=5)) as c:
        first, rtf, wav = await _speak(c, cfg, h)
        question = wav   # stands in for the person's question in (c)
        res["alone"] = {"first": _r(first), "rtf": _r(rtf), "asr": _r(await _hear(c, cfg, h, wav))}
        if ccfg.get("llm_url"):
            lh = {"Authorization": f"Bearer {ccfg['llm_key']}"} if ccfg.get("llm_key") else {}
            model = await chat.llm_model(c, ccfg, lh)
            # (b) without the rule: the load runs straight on, as it did before V01.0.225
            started = asyncio.Event()
            task = asyncio.ensure_future(_load(c, ccfg, lh, model, started))
            try:
                await asyncio.wait_for(started.wait(), 60)
                first, rtf, wav = await _speak(c, cfg, h)
                asr = await _hear(c, cfg, h, wav)
                res["load"] = {"first": _r(first), "rtf": _r(rtf), "asr": _r(asr), "load_ran": not task.done()}
            finally:
                task.cancel()
                try:
                    await task
                except BaseException:
                    pass
            # (c) with the rule: the same load as background work, it has to give way. As in a real
            # conversation the recognition of the question comes first (it already stops the load);
            # measuring speech output cold under load would count the first moments before the stop.
            started = asyncio.Event()
            job = asyncio.ensure_future(run("Vorrang-Test", lambda: _load(c, ccfg, lh, model, started), retries=0,
                                            sleep=sleep))
            try:
                await asyncio.wait_for(started.wait(), GRACE + 90)
                asr = await _hear(c, cfg, h, question)
                if asr is None:   # no recognition: the speech output itself has to stop the load
                    mark()
                await asyncio.sleep(POLL * 2)
                first, rtf, wav = await _speak(c, cfg, h)
                stopped = job.done() and not job.cancelled() and isinstance(job.exception(), Busy)
                res["vorrang"] = {"first": _r(first), "rtf": _r(rtf), "asr": _r(asr), "stopped": stopped}
            finally:
                job.cancel()
                try:
                    await job
                except BaseException:
                    pass
        if cfg["tts"].get("backend") == "vllm-omni":
            res["people"] = await _people(c, cfg, h)
            res["people_verdict"] = people_verdict(res["people"])
    res["verdict"] = verdict(res)
    return res


def test_state(now=None):
    import stufe
    return {"running": _test["running"], "result": _test["result"], "today": today(now), "people": stufe.today()}


def start_test():
    """Starts measure() once (a second start while it runs is refused by the caller)."""
    async def go():
        try:
            _test["result"] = await measure()
        except Exception as e:
            _test["result"] = {"t": int(time.time()), "error": f"{type(e).__name__}: {e}"[:200]}
        finally:
            _test["running"] = False
            print("vorrang: Test fertig", (_test["result"] or {}).get("verdict", {}).get("title", {}).get("de", "")
                  or (_test["result"] or {}).get("error", ""), flush=True)
    _test["running"] = True
    asyncio.ensure_future(go())
