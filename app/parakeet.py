"""Second recognizer: parakeet-primeline (German fine-tune of NVIDIA Parakeet TDT 0.6B v3),
int8 ONNX on the CPU via sherpa-onnx. Chosen in the panel (asr.recognizer = "parakeet");
then the Qwen3-ASR engine stays off and both ASR front ends (asr_proxy.py, asr_server.py)
transcribe with this instead. Idea and the long-audio handling come from
github.com/winidi/dictate (MIT).

No GPU, ~1 GiB RAM, very fast; no context words (asr.context is ignored) and no streaming
of partial text (a stream gets the whole text as one piece).
"""
import subprocess
import threading
import time

import numpy as np

REPO = "flozen1981/parakeet-primeline-onnx"
REVISION = "d548e25b9bfe559aa274f361892dc4ed5d64743a"  # pinned, as tested by dictate
FILES = ["encoder.int8.onnx", "encoder.int8.onnx.data", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt"]
NAME = "primeline/parakeet-primeline (int8, CPU)"
RATE = 16000
THREADS = 4
# The encoder fails on more than ~400 s and its memory grows quadratically before that
# (180 s ~ 3.5 GB), so long recordings are decoded in pieces cut at a quiet spot.
MAX_PIECE_S = 90
RETRY_PIECE_S = 20
TARGET_PEAK = 0.5   # quiet recordings come back empty; raise them to this peak
MAX_GAIN = 30.0


def download():
    from huggingface_hub import snapshot_download
    return snapshot_download(REPO, revision=REVISION, allow_patterns=FILES)


class Recognizer:
    def __init__(self):
        self.status = "loading"  # loading | ready | error
        self.error = None
        self.rec = None
        self.lock = threading.Lock()
        self.load_seconds = None

    def load(self):
        t0 = time.time()
        try:
            import sherpa_onnx
            d = download()
            rec = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=f"{d}/encoder.int8.onnx", decoder=f"{d}/decoder.int8.onnx",
                joiner=f"{d}/joiner.int8.onnx", tokens=f"{d}/tokens.txt",
                model_type="nemo_transducer", num_threads=THREADS, decoding_method="greedy_search")
            for _ in range(2):  # warm-up: the first decode is about twice as slow
                s = rec.create_stream()
                s.accept_waveform(RATE, np.zeros(RATE, dtype=np.float32))
                rec.decode_stream(s)
            self.rec = rec
            self.status = "ready"
            self.load_seconds = round(time.time() - t0, 1)
            print(f"parakeet ready in {self.load_seconds} s", flush=True)
        except Exception as e:
            self.status, self.error = "error", f"{type(e).__name__}: {e}"
            print(f"parakeet failed to load: {self.error}", flush=True)

    def load_in_background(self):
        threading.Thread(target=self.load, daemon=True).start()

    def transcribe_file(self, path):
        """Any audio ffmpeg reads -> (text, seconds of audio)."""
        audio = read_audio(path)
        with self.lock:
            parts = []
            for piece in split(audio):
                text = self._decode(piece)
                # now and then a long piece that clearly holds speech comes back empty; shorter ones decode
                if not text and len(piece) > RETRY_PIECE_S * RATE:
                    text = " ".join(t for t in map(self._decode, split(piece, RETRY_PIECE_S)) if t)
                parts.append(text)
        return " ".join(p for p in parts if p), len(audio) / RATE

    def _decode(self, piece):
        peak = float(np.abs(piece).max()) if len(piece) else 0.0
        if 0.0 < peak < TARGET_PEAK:
            piece = piece * min(TARGET_PEAK / peak, MAX_GAIN)
        s = self.rec.create_stream()
        s.accept_waveform(RATE, piece)
        self.rec.decode_stream(s)
        return s.result.text.strip()


MAX_AUDIO_S = 2 * 3600  # a small compressed file can unpack to hours of samples in RAM


def read_audio(path):
    run = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", path, "-t", str(MAX_AUDIO_S),
                          "-ac", "1", "-ar", str(RATE),
                          "-f", "s16le", "-"], capture_output=True, timeout=300)
    if run.returncode != 0:
        raise ValueError(f"unsupported audio: {run.stderr.decode(errors='replace').strip()[-200:] or 'ffmpeg failed'}")
    return np.frombuffer(run.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def split(audio, max_s=MAX_PIECE_S):
    """Pieces of at most max_s seconds, each cut at the quietest spot near its end."""
    search_s = min(15, max_s / 2)
    max_n, search_n, win_n = int(max_s * RATE), int(search_s * RATE), int(0.4 * RATE)
    while len(audio) > max_n:
        tail = audio[max_n - search_n:max_n]
        n = len(tail) // win_n
        energy = (tail[:n * win_n].reshape(n, win_n) ** 2).mean(axis=1)
        cut = max_n - search_n + int(energy.argmin()) * win_n + win_n // 2
        yield audio[:cut]
        audio = audio[cut:]
    yield audio


def sse(text, seconds):
    """The whole text as one OpenAI-style transcription stream (the format vLLM sends)."""
    import json
    chunk = {"object": "transcription.chunk", "choices": [{"delta": {"content": text}}]}
    usage = {"object": "transcription.chunk", "choices": [], "usage": {"seconds": round(seconds, 2)}}
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\ndata: {json.dumps(usage)}\n\ndata: [DONE]\n\n"
