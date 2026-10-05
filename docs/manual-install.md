# Qwen3-ASR + Qwen3-TTS on DGX Spark

Target: NVIDIA DGX Spark (GB10, Grace aarch64 + Blackwell sm_121, DGX OS / Ubuntu 24.04, CUDA 13 driver, 128 GB unified memory).

This guide is derived from the two repos (qwen-asr 0.0.6, qwen-tts 0.1.1) plus Spark-specific reports. It has **not yet been run on a Spark**; the commands at the end of each section tell you within a minute whether it worked.

## Gotchas that break the README instructions on Spark

1. **`pip install qwen-tts` / `qwen-asr` gives you CPU-only torch.** On PyPI, the aarch64 torch wheel has no CUDA. Install torch and torchaudio from the PyTorch **cu130** index *first*, and keep that index as an extra index so later installs don't swap it out.
2. **torchaudio from the wrong index fails to load** (`OSError: Could not load ... libtorchaudio.so`). Same fix: torch and torchaudio together from cu130 ([NVIDIA forum thread](https://forums.developer.nvidia.com/t/support-for-qwen3-tts-on-dgx-spark-gb10-torchaudio-installation-failure-on-arm64/359663)).
3. **Skip flash-attn.** There is no aarch64 wheel, it is a long source build, and it is reported not to compile for sm_121. Both packages support PyTorch SDPA, so pass `attn_implementation="sdpa"`. The TTS README and examples hardcode `"flash_attention_2"`; change that.
4. **Separate venvs.** qwen-asr pins `transformers==4.57.6`, qwen-tts pins `transformers==4.57.3`. They cannot share an environment.
5. **Don't use `pip install "qwen-asr[vllm]"` on Spark.** It pins `vllm==0.14.0` which pins `torch==2.9.1`, and pip will pull the CPU torch from PyPI. For vLLM use the official CUDA 13 container instead (section 2b).
6. **Unified memory:** vLLM's `--gpu-memory-utilization` is a share of the whole 128 GB pool the OS also lives in. These are small models (0.6B–1.7B); 0.2–0.3 is plenty.

## 0. System packages (once)

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev git ffmpeg sox libsox-fmt-all libsndfile1
nvidia-smi   # should show GB10 and a CUDA 13.x driver
```

Optional, pre-download weights (otherwise they download on first use):

```bash
python3 -m venv ~/venvs/hf && ~/venvs/hf/bin/pip install -U "huggingface_hub[cli]"
~/venvs/hf/bin/hf download Qwen/Qwen3-ASR-1.7B
~/venvs/hf/bin/hf download Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice
```

## 1. Qwen3-TTS

```bash
python3 -m venv ~/venvs/qwen3-tts
source ~/venvs/qwen3-tts/bin/activate
pip install -U pip wheel setuptools

# CUDA torch + torchaudio for aarch64 / CUDA 13
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu130
export PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cu130

pip install -U qwen-tts

# torch must still be the CUDA build
python -c "import torch, torchaudio; print(torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.get_device_name(0)); print(torch.cuda.get_arch_list())"
```

Expect `True` and `NVIDIA GB10`. If `torch.version.cuda` prints `None`, pip replaced torch with the CPU build: rerun the cu130 install line with `--force-reinstall`.

A warning that sm_121 isn't in the arch list is harmless as long as `sm_120` is listed (sm_120 kernels run on sm_121).

### Smoke test

```bash
cat > tts_smoke.py <<'EOF'
import time, torch, soundfile as sf
from qwen_tts import Qwen3TTSModel

tts = Qwen3TTSModel.from_pretrained(
    "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    device_map="cuda:0",
    dtype=torch.bfloat16,
    attn_implementation="sdpa",   # not flash_attention_2 on Spark
)
print("speakers:", tts.get_supported_speakers())
t0 = time.time()
wavs, sr = tts.generate_custom_voice(
    text="Hello from the DGX Spark. This is Qwen3 text to speech.",
    language="English",
    speaker="Ryan",
)
torch.cuda.synchronize()
print(f"generated {len(wavs[0])/sr:.1f}s of audio in {time.time()-t0:.1f}s")
sf.write("tts_out.wav", wavs[0], sr)
EOF
python tts_smoke.py
```

Web demo (it defaults to FlashAttention, so turn it off): `qwen-tts-demo Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice --no-flash-attn --ip 0.0.0.0 --port 8000`, then open `http://<spark-ip>:8000`.

If you want something faster and production-shaped later, there is a community Spark container with CUDA graphs and an OpenAI-compatible API: [mARTin-B78/dgx-spark-faster-qwen3-tts](https://github.com/mARTin-B78/dgx-spark-faster-qwen3-tts) (reported RTF ~0.8 on the 1.7B model).

## 2a. Qwen3-ASR, transformers backend (simplest)

```bash
python3 -m venv ~/venvs/qwen3-asr
source ~/venvs/qwen3-asr/bin/activate
pip install -U pip wheel setuptools
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu130
export PIP_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cu130
pip install -U qwen-asr          # NOT qwen-asr[vllm]
python -c "import torch; print(torch.version.cuda, torch.cuda.is_available())"
```

### Smoke test (also round-trips the TTS output)

```bash
cat > asr_smoke.py <<'EOF'
import sys, torch
from qwen_asr import Qwen3ASRModel

model = Qwen3ASRModel.from_pretrained(
    "Qwen/Qwen3-ASR-1.7B",
    dtype=torch.bfloat16,
    device_map="cuda:0",
    attn_implementation="sdpa",
    max_inference_batch_size=8,
    max_new_tokens=256,
)
audio = sys.argv[1] if len(sys.argv) > 1 else \
    "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-ASR-Repo/asr_en.wav"
r = model.transcribe(audio=audio, language=None)[0]
print(r.language, "|", r.text)
EOF
python asr_smoke.py                 # sample clip from Qwen
python asr_smoke.py tts_out.wav     # the file TTS just made
```

Timestamps: add `forced_aligner="Qwen/Qwen3-ForcedAligner-0.6B"` and `forced_aligner_kwargs=dict(dtype=torch.bfloat16, device_map="cuda:0", attn_implementation="sdpa")`, then `transcribe(..., return_time_stamps=True)`.

## 2b. Qwen3-ASR, vLLM server (fast, OpenAI-compatible, streaming)

vLLM has native Qwen3-ASR support. On Spark, use vLLM's CUDA 13 image, which the [vLLM DGX Spark post](https://vllm.ai/blog/2026-06-01-vllm-dgx-spark) recommends because it is built for sm_121:

```bash
docker run --rm -it --gpus all --ipc=host -p 8000:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  vllm/vllm-openai:cu130-nightly \
  Qwen/Qwen3-ASR-1.7B --gpu-memory-utilization 0.25
```

(If the image's entrypoint isn't `vllm serve`, put `vllm serve` before the model name. Audio extras ship in the image; if it complains, `pip install "vllm[audio]"` inside it.) Pin a dated tag or digest once it works.

Test with the OpenAI transcription API:

```bash
curl -s -o asr_en.wav https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-ASR-Repo/asr_en.wav
curl -s http://localhost:8000/v1/audio/transcriptions \
  -F model=Qwen/Qwen3-ASR-1.7B -F file=@asr_en.wav
```

## If something fails

| Symptom | Fix |
|---|---|
| `torch.cuda.is_available()` is False / `torch.version.cuda` None | CPU torch got installed. Reinstall torch+torchaudio from cu130 with `--force-reinstall`. |
| `libtorchaudio.so` won't load | torchaudio doesn't match torch. Reinstall both together from cu130. |
| `flash_attn` ImportError | Something still asks for `flash_attention_2`; change it to `sdpa`. |
| `no kernel image is available for execution on the device` | A dependency was built without sm_120/121. Check `torch.cuda.get_arch_list()`; use the cu130 wheels or an NGC container (`nvcr.io/nvidia/pytorch:25.11-py3` or newer). |
| `sox` / `SoX could not be found` warning | `sudo apt install sox libsox-fmt-all`. |
