#!/usr/bin/env bash
# Starts one vLLM engine natively (no Docker), as the speech user:
#   speech-spark-tts-engine.service  -> engine.sh main    (vllm-omni, CustomVoice / Base model)
#   speech-spark-tts-design.service  -> engine.sh design  (vllm-omni, VoiceDesign model)
#   speech-spark-asr-engine.service  -> engine.sh asr     (plain vLLM, Qwen3-ASR)
# Listens on 127.0.0.1 only; speech-spark-tts / speech-spark-asr on the public ports sit in front.
set -euo pipefail

ROLE="${1:?usage: engine.sh main|design|asr}"
CONFIG="${SPEECH_SPARK_CONFIG:-/etc/speech-spark/config.json}"
STATE_DIR="${SPEECH_SPARK_STATE:-/var/lib/speech-spark/state}"
VENV="${SPEECH_SPARK_ENGINE_VENV:-/opt/speech-spark/venv-engine}"
STATE="$STATE_DIR/speech-spark-tts-$ROLE.json"
[ "$ROLE" = asr ] && STATE="$STATE_DIR/speech-spark-asr-engine.json"
mkdir -p "$STATE_DIR"

state() {  # $1 = status, $2 = message
  jq -n --arg s "$1" --arg e "$2" --arg t "$(date -Is)" '{status: $s, error: $e, time: $t}' >"$STATE"
}
fail() { state error "$1"; echo "ERROR: $1" >&2; exit 1; }

if [ "$ROLE" = asr ]; then
  c() { jq -r ".asr.$1" "$CONFIG"; }
  SEQS=$(c engine_max_seqs); MEM0=$(c engine_mem); MEM1=0.0
  MODEL=$(c model); PORT=$(c engine_port)
else
  c() { jq -r ".tts.$1" "$CONFIG"; }
  SEQS=$(c engine_max_seqs); MEM0=$(c engine_mem_talker); MEM1=$(c engine_mem_code2wav)
  MAXLEN=$(jq -r '.tts.engine_max_model_len // 4096' "$CONFIG")
  if [ "$ROLE" = design ]; then MODEL=$(c voicedesign_model); PORT=$(c voicedesign_port)
  else MODEL=$(c model); PORT=$(c engine_port); fi
fi

[[ "$MODEL" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]] || fail "invalid model id '$MODEL'"
[[ "$PORT" =~ ^[0-9]{4,5}$ ]] || fail "invalid port '$PORT'"
[[ "$SEQS" =~ ^[0-9]{1,3}$ ]] || fail "invalid engine_max_seqs '$SEQS'"
for m in "$MEM0" "$MEM1"; do
  [[ "$m" =~ ^0?\.[0-9]+$ ]] || fail "engine memory shares must be fractions like 0.05, got '$m'"
done
# JIT kernel builds call ninja / nvcc by name; systemd gives a minimal PATH
export PATH="$VENV/bin:/usr/local/cuda/bin:$PATH"
[ -x "$VENV/bin/vllm" ] || fail "vLLM is not installed in $VENV; run install.sh"

# One engine at a time: vLLM sizes its KV cache from device-wide memory use while it starts,
# so an engine loading at the same moment eats into this one's budget (seen on GB10:
# "Available KV cache memory: 0.0 GiB"). Order: asr, main, design; each waits for the ones
# before it that are running but not ready yet, at most 20 minutes.
others=()
case "$ROLE" in
  main) others=("speech-spark-asr-engine $(jq -r .asr.engine_port "$CONFIG")") ;;
  design) others=("speech-spark-asr-engine $(jq -r .asr.engine_port "$CONFIG")"
                  "speech-spark-tts-engine $(jq -r .tts.engine_port "$CONFIG")") ;;
esac
for o in "${others[@]}"; do
  read -r ounit oport <<<"$o"
  for _ in $(seq 1 240); do
    # also wait through the other engine's restart pause, so its next start does not overlap ours
    case "$(systemctl is-active "$ounit" 2>/dev/null)" in active|activating) ;; *) break ;; esac
    curl -fs -o /dev/null "http://127.0.0.1:$oport/health" && break
    state loading "waiting for $ounit to finish starting"
    sleep 5
  done
done

# Memory guard: vLLM claims its share of the whole unified pool up front.
total_kib=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)
avail_kib=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
read -r need_gib avail_gib < <(awk -v t="$total_kib" -v a="$avail_kib" -v m0="$MEM0" -v m1="$MEM1" \
  'BEGIN { printf "%.1f %.1f\n", (m0 + m1) * t / 1048576 + 1.5, a / 1048576 }')
guard=$(jq -r '.memory.guard // true' "$CONFIG")
reserve=$(jq -r '.memory.reserve_gib // 10' "$CONFIG")
if [ "$guard" = true ] && awk -v a="$avail_gib" -v n="$need_gib" -v r="$reserve" 'BEGIN { exit !(a - n < r) }'; then
  msg="not enough unified memory: $avail_gib GiB available, engine needs ~$need_gib GiB, reserve is $reserve GiB"
  state blocked "$msg"
  echo "BLOCKED: $msg" >&2
  exit 1
fi

cached="${HF_HOME:-$HOME/.cache/huggingface}/hub/models--${MODEL//\//--}"
if [ -d "$cached/snapshots" ]; then what="loading $MODEL and warming up"
else what="downloading and loading $MODEL"; fi
state loading "$what, reserves ~$need_gib GiB"

if [ "$ROLE" = asr ]; then
  # Plain vLLM: OpenAI /v1/audio/transcriptions incl. streaming, batches parallel requests.
  # Audio is cut into model-sized clips, so a short max length keeps the KV cache small.
  export VLLM_MAX_AUDIO_CLIP_FILESIZE_MB=200
  exec "$VENV/bin/vllm" serve "$MODEL" \
    --host 127.0.0.1 --port "$PORT" \
    --served-model-name "$MODEL" \
    --gpu-memory-utilization "$MEM0" \
    --max-num-seqs "$SEQS" \
    --max-model-len 4096 \
    --max-num-batched-tokens 4096
fi

[[ "$MAXLEN" =~ ^[0-9]{3,6}$ ]] || fail "invalid engine_max_model_len '$MAXLEN'"
# A short talker context keeps its KV cache small; 4096 talker steps are minutes of audio.
overrides=$(jq -cn --argjson m0 "$MEM0" --argjson m1 "$MEM1" --argjson s "$SEQS" --argjson l "$MAXLEN" \
  '{"0": {gpu_memory_utilization: $m0, max_num_seqs: $s, max_model_len: $l}, "1": {gpu_memory_utilization: $m1, max_num_seqs: $s}}')

exec "$VENV/bin/vllm" serve "$MODEL" --omni \
  --host 127.0.0.1 --port "$PORT" \
  --trust-remote-code \
  --served-model-name "$MODEL" \
  --stage-overrides "$overrides"
