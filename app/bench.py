"""Measures speech on this box: time to first audio, speed and memory.

    sudo speech-spark-bench                 # full run, prints a report
    sudo speech-spark-bench --parallel 8    # more simultaneous requests
    sudo speech-spark-bench --audio a.wav   # ASR with your own recording instead of TTS output

The panel runs the same measurement from the "System" tab. Results are kept in
/var/lib/speech-spark/state/bench-latest.json so the panel shows the last run.
Measures through the public ports, so it sees what apps see (key, proxy and all).
"""
import argparse
import asyncio
import base64
import json
import os
import struct
import subprocess
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_config, mem_available_gib  # noqa: E402

STATE_DIR = os.environ.get("SPEECH_SPARK_STATE", "/var/lib/speech-spark/state")
RESULT = os.path.join(STATE_DIR, "bench-latest.json")
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

        res["memory_after"] = memory_snapshot()
        res["duration_s"] = round(time.time() - res["time"], 1)
        await self.client.aclose()
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(RESULT + ".tmp", "w") as f:
                json.dump(res, f, indent=2)
            os.replace(RESULT + ".tmp", RESULT)
        except OSError as e:
            self.log(f"could not save {RESULT}: {e}")
        return res


def fmt(v, digits=2):
    return "–" if v is None else f"{v:.{digits}f}"


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
