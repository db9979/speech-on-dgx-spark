"""Measures speech on this box: time to first audio, speed and memory.

    sudo speech-spark-bench                 # full run, prints a report
    sudo speech-spark-bench --parallel 8    # more simultaneous requests
    sudo speech-spark-bench --audio a.wav   # ASR with your own recording instead of TTS output

The panel runs the same measurement under Zustand → Prüfen. Results are kept in
/var/lib/speech-spark/state/bench-latest.json so the panel shows the last run; the last ten runs'
key numbers go to bench-history.json for the comparison. rate() gives every number a level and a
sentence what it means (fixed rules, the panel only shows them).
Measures through the public ports, so it sees what apps see (key, proxy and all).
"""
import argparse
import asyncio
import base64
import json
import os
import re
import struct
import subprocess
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_config, mem_available_gib  # noqa: E402

STATE_DIR = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
RESULT = os.path.join(STATE_DIR, "bench-latest.json")
HISTORY = os.path.join(STATE_DIR, "bench-history.json")
KEEP_RUNS = 10
TEXT = ("Guten Morgen. Dies ist ein Test der Sprachausgabe auf der DGX Spark. Wir messen, wie schnell "
        "der erste Ton kommt, wie lange der ganze Satz braucht und wie viele Anfragen gleichzeitig "
        "flüssig laufen. Danach hört die Spracherkennung zu und schreibt alles wieder auf.")
PCM_BYTES_PER_S = 24000 * 2
UNITS = ["speech-spark-asr", "speech-spark-asr-engine", "speech-spark-tts", "speech-spark-tts-engine",
         "speech-spark-tts-design"]


def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def wav_seconds(data):
    """Length of a PCM WAV, also when the header has no valid size (streamed WAV)."""
    try:
        channels, rate = struct.unpack("<HI", data[22:28])
        bits = struct.unpack("<H", data[34:36])[0]
        pos = data.index(b"data") + 8
        return (len(data) - pos) / (rate * channels * bits / 8)
    except Exception:
        return None


def avg(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 3) if xs else None


def memory_snapshot():
    """Per unit: cgroup memory (CPU side) and GPU memory of its processes as nvidia-smi reports it."""
    gpu = {}
    for line in run(["nvidia-smi", "--query-compute-apps=pid,used_memory",
                     "--format=csv,noheader,nounits"]).splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) == 2 and parts[1].replace(".", "").isdigit():
            gpu[parts[0]] = float(parts[1]) / 1024
    out = {"mem_available_gib": round(mem_available_gib(), 1), "units": {}}
    for unit in UNITS:
        props = dict(l.split("=", 1) for l in run(["systemctl", "show", unit, "-p",
                                                   "ActiveState,MemoryCurrent,ControlGroup"]).splitlines() if "=" in l)
        if props.get("ActiveState") != "active":
            continue
        pids = run(["cat", f"/sys/fs/cgroup{props.get('ControlGroup', '')}/cgroup.procs"]).split()
        cur = props.get("MemoryCurrent", "")
        out["units"][unit] = {
            "ram_gib": round(int(cur) / 2**30, 1) if cur.isdigit() else None,
            "gpu_gib": round(sum(gpu.get(p, 0) for p in pids), 1) if gpu else None,
        }
    return out


class Bench:
    def __init__(self, parallel=4, repeats=3, audio=None, log=print):
        self.cfg = load_config()
        key = self.cfg.get("api", {}).get("key", "")
        self.headers = {"Authorization": f"Bearer {key}"} if key else {}
        self.parallel, self.repeats, self.audio, self.log = parallel, repeats, audio, log
        self.client = httpx.AsyncClient(timeout=900)

    def url(self, svc, path):
        return f"http://127.0.0.1:{self.cfg[svc]['port']}{path}"

    async def ready(self, svc):
        if not self.cfg[svc].get("enabled"):
            return "disabled"
        try:
            return (await self.client.get(self.url(svc, "/health"), timeout=5)).json().get("status")
        except Exception:
            return "unreachable"

    # ------------------------------------------------------------ TTS
    async def tts_stream(self):
        body = {"input": TEXT, "language": "German", "stream": True, "response_format": "pcm"}
        t0 = time.time()
        first, pcm = None, 0
        async with self.client.stream("POST", self.url("tts", "/v1/audio/speech"), json=body,
                                      headers=self.headers) as r:
            if r.status_code != 200:
                raise RuntimeError(f"TTS {r.status_code}: {(await r.aread())[:200]!r}")
            buf = b""
            async for chunk in r.aiter_raw():
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if line.startswith(b"data:") and b"speech.audio.delta" in line:
                        n = len(base64.b64decode(json.loads(line[5:])["audio"]))
                        if n and first is None:
                            first = time.time() - t0
                        pcm += n
        total = time.time() - t0
        return {"ttfa_s": first, "total_s": total, "audio_s": pcm / PCM_BYTES_PER_S}

    async def tts_wav(self, text=TEXT):
        t0 = time.time()
        r = await self.client.post(self.url("tts", "/v1/audio/speech"), headers=self.headers,
                                   json={"input": text, "language": "German", "response_format": "wav"})
        if r.status_code != 200:
            raise RuntimeError(f"TTS {r.status_code}: {r.text[:200]}")
        total = time.time() - t0
        return {"ttfa_s": None, "total_s": total, "audio_s": wav_seconds(r.content), "wav": r.content}

    async def bench_tts(self):
        streaming = self.cfg["tts"].get("backend") == "vllm-omni"
        one = self.tts_stream if streaming else self.tts_wav
        self.log("TTS: warm-up")
        await one()
        singles = []
        for i in range(self.repeats):
            r = await one()
            singles.append(r)
            self.log(f"TTS {i + 1}/{self.repeats}: first audio {fmt(r['ttfa_s'])} s, "
                     f"{fmt(r['audio_s'])} s audio in {fmt(r['total_s'])} s")
        self.log(f"TTS: {self.parallel} requests at once")
        t0 = time.time()
        par = await asyncio.gather(*[one() for _ in range(self.parallel)])
        wall = time.time() - t0
        return {
            "streaming": streaming,
            "single": {"ttfa_s": avg(r["ttfa_s"] for r in singles),
                       "total_s": avg(r["total_s"] for r in singles),
                       "audio_s": avg(r["audio_s"] for r in singles),
                       "rtf": avg(r["total_s"] / r["audio_s"] for r in singles if r["audio_s"])},
            "parallel": {"n": self.parallel, "wall_s": round(wall, 3),
                         "ttfa_s": avg(r["ttfa_s"] for r in par),
                         "ttfa_max_s": max((r["ttfa_s"] for r in par if r["ttfa_s"] is not None), default=None),
                         "x_realtime": round(sum(r["audio_s"] or 0 for r in par) / wall, 2)},
        }

    # ------------------------------------------------------------ ASR
    async def asr_once(self, wav, name="bench.wav"):
        t0 = time.time()
        r = await self.client.post(self.url("asr", "/v1/audio/transcriptions"), headers=self.headers,
                                   files={"file": (name, wav)}, data={"language": "de"})
        if r.status_code != 200:
            raise RuntimeError(f"ASR {r.status_code}: {r.text[:200]}")
        return time.time() - t0, r.json().get("text", "")

    async def bench_asr(self, wav, audio_s, name):
        self.log("ASR: warm-up")
        await self.asr_once(wav, name)
        times, text = [], ""
        for i in range(self.repeats):
            dt, text = await self.asr_once(wav, name)
            times.append(dt)
            self.log(f"ASR {i + 1}/{self.repeats}: {fmt(audio_s)} s audio in {fmt(dt)} s")
        n = self.parallel * 2
        self.log(f"ASR: {n} requests at once")
        t0 = time.time()
        await asyncio.gather(*[self.asr_once(wav, name) for _ in range(n)])
        wall = time.time() - t0
        return {
            "audio_s": round(audio_s, 2) if audio_s else None,
            "single": {"total_s": avg(times), "rtf": avg(t / audio_s for t in times) if audio_s else None},
            "parallel": {"n": n, "wall_s": round(wall, 3),
                         "x_realtime": round(n * audio_s / wall, 1) if audio_s else None},
            "heard": text,
        }

    # ------------------------------------------------------------ all
    async def run(self):
        c = self.cfg
        res = {"time": time.time(), "host": os.uname().nodename,
               "config": {"asr": {k: c["asr"].get(k) for k in ("enabled", "model", "backend", "engine_mem",
                                                               "engine_max_seqs")},
                          "tts": {k: c["tts"].get(k) for k in ("enabled", "model", "backend", "engine_mem_talker",
                                                               "engine_mem_code2wav", "engine_max_seqs",
                                                               "voicedesign_enabled")}},
               "qwen38_active": [u for u in run(["systemctl", "list-units", "qwen38-*", "--state=active",
                                                 "--no-legend", "--plain"]).split() if u.endswith(".service")],
               "tts": None, "asr": None, "errors": []}
        try:
            res["gpu_name"] = run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
        except Exception:
            pass
        res["memory"] = memory_snapshot()

        tts_state, asr_state = await self.ready("tts"), await self.ready("asr")
        if tts_state == "ready":
            try:
                res["tts"] = await self.bench_tts()
            except Exception as e:
                res["errors"].append(f"TTS: {e}")
        else:
            res["errors"].append(f"TTS not measured: {tts_state}")

        if asr_state == "ready":
            try:
                if self.audio:
                    with open(self.audio, "rb") as f:
                        wav, name = f.read(), os.path.basename(self.audio)
                elif tts_state == "ready":
                    self.log("ASR: making a test recording with TTS")
                    wav, name = (await self.tts_wav())["wav"], "bench.wav"
                else:
                    raise RuntimeError("needs TTS for a test recording, or --audio FILE")
                res["asr"] = await self.bench_asr(wav, wav_seconds(wav), name)
            except Exception as e:
                res["errors"].append(f"ASR: {e}")
        else:
            res["errors"].append(f"ASR not measured: {asr_state}")

        if res["asr"] and not self.audio:
            res["asr"]["accuracy"] = word_accuracy(res["asr"].get("heard", ""), TEXT)
        res["memory_after"] = memory_snapshot()
        res["duration_s"] = round(time.time() - res["time"], 1)
        await self.client.aclose()
        history = load_history()
        res["previous"] = history[-1] if history else None
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            save_history(history + [{"time": round(res["time"]), "qwen38": bool(res["qwen38_active"]),
                                     "values": values(res)}])
        except OSError as e:
            self.log(f"could not save {HISTORY}: {e}")
        try:
            with open(RESULT + ".tmp", "w") as f:
                json.dump(res, f, indent=2)
            os.replace(RESULT + ".tmp", RESULT)
        except OSError as e:
            self.log(f"could not save {RESULT}: {e}")
        return res


def fmt(v, digits=2):
    return "–" if v is None else f"{v:.{digits}f}"


# ------------------------------------------------------------ how good is it
# Fixed rules, the panel only shows them. Levels: top (sehr gut), ok (gut), warn (knapp), bad.
LEVELS = ("top", "ok", "warn", "bad")


def _words(text):
    return re.findall(r"\w+", (text or "").lower())


def word_accuracy(heard, reference):
    """Share of the reference's words that came back right (1 - word error rate), 0..1."""
    ref, hyp = _words(reference)[:400], _words(heard)[:400]
    if not ref:
        return None
    row = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, row[0] = row[0], i
        for j, h in enumerate(hyp, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (r != h))
    return round(max(0.0, 1 - row[-1] / len(ref)), 3)


def values(r):
    """The numbers that get a rating, by key (also kept in the history for the comparison)."""
    t, a, m = r.get("tts") or {}, r.get("asr") or {}, r.get("memory_after") or {}
    ts, tp, as_, ap = t.get("single") or {}, t.get("parallel") or {}, a.get("single") or {}, a.get("parallel") or {}
    v = {"tts_first": ts.get("ttfa_s"),
         "tts_speed": round(1 / ts["rtf"], 2) if ts.get("rtf") else None,
         "tts_par": tp.get("x_realtime"), "tts_par_n": tp.get("n"), "tts_par_first": tp.get("ttfa_max_s"),
         "asr_time": as_.get("total_s"), "asr_audio": a.get("audio_s"), "asr_acc": a.get("accuracy"),
         "asr_par": ap.get("x_realtime"), "asr_par_n": ap.get("n"),
         "mem_free": m.get("mem_available_gib")}
    return {k: x for k, x in v.items() if isinstance(x, (int, float)) and not isinstance(x, bool)}


def _num(v, digits=2):
    return f"{v:.{digits}f}".replace(".", ",")


def _step(v, limits, higher_is_better=True):
    """limits: three borders between top/ok, ok/warn, warn/bad."""
    for level, border in zip(LEVELS, limits):
        if (v >= border) if higher_is_better else (v <= border):
            return level
    return "bad"


WORDS = {"top": "sehr gut", "ok": "gut", "warn": "knapp", "bad": "zu langsam"}


def _parallel(key, label, x, n, what):
    level = _step(x / n, (1.5, 1.0, 0.7))
    fluent = min(n, int(x))
    if level in ("top", "ok"):
        why = f"Für {n} flüssige {what} braucht es {n}×, gemessen sind {_num(x, 1)}×: alle gleichzeitig gehen."
    else:
        why = (f"Für {n} flüssige {what} braucht es {n}×. "
               + (f"{fluent} gleichzeitig gehen flüssig, mehr können kurz stocken." if fluent
                  else "Schon zwei gleichzeitig können stocken."))
    return {"key": key, "n": n, "label": label, "value": f"{_num(x, 1)}× gesamt", "level": level,
            "word": "stockt" if level == "bad" else WORDS[level], "why": why}


def rate(r, previous=None):
    """Per value a level and one sentence what it means, plus one sentence for the whole run."""
    v = values(r)
    prev = (previous or {}).get("values") or {}
    tts, asr, mem = [], [], []
    if "tts_first" in v:
        x = v["tts_first"]
        tts.append({"key": "tts_first", "label": "Erster Ton nach", "value": f"{_num(x)} s",
                    "level": _step(x, (0.5, 1.0, 2.0), False),
                    "why": "Unter 1 s wirkt die Antwort sofort, ab 2 s merkt man das Warten."})
    if "tts_speed" in v:
        x = v["tts_speed"]
        level = _step(x, (2.0, 1.3, 1.0))
        tts.append({"key": "tts_speed", "label": "Tempo", "value": f"{_num(x, 1)}× Echtzeit", "level": level,
                    "word": "stockt" if level == "bad" else None,
                    "why": "Ab 1× läuft die Stimme ohne Stocken, ab 2× ist genug Luft, auch wenn qwen38 rechnet."})
    if "tts_par" in v and v.get("tts_par_n"):
        tts.append(_parallel("tts_par", f"{v['tts_par_n']} gleichzeitig", v["tts_par"], v["tts_par_n"], "Stimmen"))
    if "tts_par_first" in v and v.get("tts_par_n"):
        x = v["tts_par_first"]
        level = _step(x, (1.0, 1.5, 3.0), False)
        tts.append({"key": "tts_par_first", "n": v["tts_par_n"], "label": f"Erster Ton bei {v['tts_par_n']} gleichzeitig",
                    "value": f"bis {_num(x)} s", "level": level,
                    "word": {"warn": "spürbar", "bad": "zäh"}.get(level),
                    "why": "So lange wartet der, der als Letzter drankommt. Bis 1,5 s fällt das kaum auf."})
    if "asr_time" in v:
        x, sec = v["asr_time"], v.get("asr_audio")
        why = "Unter 1,5 s für einen langen Satz fühlt sich sofort an, ab 3 s wartet man."
        if sec and x:
            why += f" {_num(sec / x, 0)}× schneller als gesprochen."
        asr.append({"key": "asr_time", "label": (f"{_num(sec, 1)} s Sprache erkannt in" if sec else "Erkannt in"),
                    "value": f"{_num(x)} s", "level": _step(x, (1.5, 3.0, 5.0), False), "why": why})
    if "asr_acc" in v:
        x = v["asr_acc"]
        level = _step(x, (0.95, 0.90, 0.85))
        asr.append({"key": "asr_acc", "label": "Richtig verstanden", "value": f"{_num(x * 100, 0)} % der Wörter",
                    "level": level, "word": "schlecht" if level == "bad" else None, "fmt": "pct",
                    "why": "Ab 95 % sind nur Kleinigkeiten falsch, unter 85 % versteht der Assistent Fragen oft falsch."})
    if "asr_par" in v and v.get("asr_par_n"):
        asr.append(_parallel("asr_par", f"{v['asr_par_n']} gleichzeitig", v["asr_par"], v["asr_par_n"], "Erkennungen"))
    if "mem_free" in v:
        x = v["mem_free"]
        level = "ok" if x >= 14 else "warn" if x >= 10 else "bad"
        why = "Unter etwa 8 GiB beendet DGX OS Programme, ab 14 GiB ist sicher Luft."
        if level != "ok":
            why += " Hilft: kleineres Modell oder weniger Speicher für qwen38."
        mem.append({"key": "mem_free", "label": "Frei auf dem Spark", "value": f"{_num(x, 1)} GiB", "level": level,
                    "word": "kritisch" if level == "bad" else None, "why": why})
    groups = [g for g in ({"name": "Sprachausgabe", "rows": tts}, {"name": "Spracherkennung", "rows": asr},
                          {"name": "Speicher", "rows": mem}) if g["rows"]]
    rows = [row for g in groups for row in g["rows"]]
    for row in rows:
        row["word"] = row.get("word") or WORDS[row["level"]]
        old = prev.get(row["key"])
        if isinstance(old, (int, float)):
            row["before"] = _before(row, old)
    return {"verdict": _verdict(r, rows), "groups": groups}


def _before(row, old):
    if row.get("fmt") == "pct":
        return f"{_num(old * 100, 0)} %"
    unit = {"tts_speed": "×", "tts_par": "×", "asr_par": "×", "mem_free": " GiB"}.get(row["key"], " s")
    return f"{_num(old, 1 if unit != ' s' else 2)}{unit}"


SINGLE = ("tts_first", "tts_speed", "asr_time", "asr_acc")
SHORT = {"tts_first": "erster Ton", "tts_speed": "Tempo der Stimme", "tts_par": "Stimmen gleichzeitig",
         "tts_par_first": "erster Ton bei mehreren", "asr_time": "Tempo der Erkennung", "asr_acc": "Verständnis",
         "asr_par": "Erkennung gleichzeitig", "mem_free": "freier Speicher"}


def _verdict(r, rows):
    errors = r.get("errors") or []
    worst = max((LEVELS.index(row["level"]) for row in rows), default=3 if errors else 0)
    level = LEVELS[worst]
    weak = [row for row in rows if row["level"] in ("warn", "bad")]
    single_fine = all(row["level"] in ("top", "ok") for row in rows if row["key"] in SINGLE)
    if not rows:
        title = "Nichts gemessen."
        level = "bad"
    elif not weak:
        title = "Alles flüssig, auch bei mehreren gleichzeitig." if any(
            row["key"].endswith("_par") for row in rows) else "Alles flüssig."
    elif level == "bad":
        title = "Hier hakt es: " + ", ".join(SHORT[row["key"]] for row in weak if row["level"] == "bad") + "."
    elif single_fine and any(row.get("n") for row in weak):
        n = min(row["n"] for row in weak if row.get("n"))
        title = f"Gut für ein Gespräch, bei {n} gleichzeitig wird es knapp."
    elif single_fine:
        title = "Flüssig, aber der Speicher ist knapp."
    else:
        title = "Läuft, aber an einer Stelle knapp." if len(weak) == 1 else "Läuft, aber an mehreren Stellen knapp."
    detail = []
    if r.get("qwen38_active"):
        detail.append(f"{', '.join(u.removesuffix('.service') for u in r['qwen38_active'][:4])} lief während der "
                      "Messung, ohne qwen38 sind die Werte meist besser.")
    if weak:
        detail.append(("Knapp" if level == "warn" else "Schwach") + ": " + ", ".join(SHORT[row["key"]] for row in weak) + ".")
    if errors:
        detail.append("Nicht alles gemessen, Einzelheiten unter Rohwerte.")
        level = "bad" if not rows else max(level, "warn", key=LEVELS.index)
    return {"level": level, "title": title, "detail": " ".join(detail)}


def load_history():
    try:
        with open(HISTORY) as f:
            d = json.load(f)
        return [x for x in d if isinstance(x, dict) and isinstance(x.get("values"), dict)][-KEEP_RUNS:] \
            if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def save_history(items):
    tmp = HISTORY + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w") as f:
        json.dump(items[-KEEP_RUNS:], f)
    os.replace(tmp, HISTORY)


def report(r):
    lines = [f"Speech on DGX Spark, measured {time.strftime('%Y-%m-%d %H:%M', time.localtime(r['time']))} "
             f"on {r['host']} ({r.get('gpu_name') or 'GPU ?'})"]
    lines.append(f"qwen38 running: {', '.join(r['qwen38_active']) or 'nothing'}")
    t = r.get("tts")
    if t:
        s, p = t["single"], t["parallel"]
        lines += ["", f"TTS  {r['config']['tts']['model']} ({r['config']['tts']['backend']})",
                  f"  one request:    first audio {fmt(s['ttfa_s'])} s, {fmt(s['audio_s'], 1)} s audio in "
                  f"{fmt(s['total_s'])} s (RTF {fmt(s['rtf'])}, below 1 = faster than real time)",
                  f"  {p['n']} at once:      first audio avg {fmt(p['ttfa_s'])} s / max {fmt(p['ttfa_max_s'])} s, "
                  f"{fmt(p['x_realtime'], 1)}x real time in total"]
    a = r.get("asr")
    if a:
        s, p = a["single"], a["parallel"]
        lines += ["", f"ASR  {r['config']['asr']['model']} ({r['config']['asr']['backend']})",
                  f"  one request:    {fmt(a['audio_s'], 1)} s audio in {fmt(s['total_s'])} s (RTF {fmt(s['rtf'], 3)})",
                  f"  {p['n']} at once:     {fmt(p['wall_s'])} s in total, {fmt(p['x_realtime'], 1)}x real time",
                  f"  heard: {a['heard'][:120]}"]
        if a.get("accuracy") is not None:
            lines.append(f"  words right: {fmt(a['accuracy'] * 100, 0)} %")
    m = r.get("memory_after") or {}
    lines += ["", f"Memory: {fmt(m.get('mem_available_gib'), 1)} GiB available"]
    for unit, u in (m.get("units") or {}).items():
        lines.append(f"  {unit:26} RAM {fmt(u['ram_gib'], 1)} GiB   GPU {fmt(u['gpu_gib'], 1)} GiB")
    for e in r["errors"]:
        lines.append(f"! {e}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--parallel", type=int, default=4, help="simultaneous TTS requests (ASR uses twice as many)")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--audio", help="WAV/MP3/... file for the ASR measurement")
    ap.add_argument("--json", action="store_true", help="print the raw result")
    args = ap.parse_args()
    res = asyncio.run(Bench(args.parallel, args.repeats, args.audio,
                            log=lambda m: print("  " + m, file=sys.stderr, flush=True)).run())
    print(json.dumps(res, indent=2) if args.json else "\n" + report(res))


if __name__ == "__main__":
    main()
