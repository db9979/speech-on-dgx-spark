#!/usr/bin/env bash
# Starts one vllm-omni TTS engine natively (no Docker), as the speech user:
#   speech-spark-tts-engine.service  -> engine.sh main    (CustomVoice / Base model)
#   speech-spark-tts-design.service  -> engine.sh design  (VoiceDesign model)
# Listens on 127.0.0.1 only; speech-spark-tts on the public port sits in front of it.
set -euo pipefail

ROLE="${1:?usage: engine.sh main|design}"
CONFIG="${SPEECH_SPARK_CONFIG:-/etc/speech-spark/config.json}"
STATE_DIR="${SPEECH_SPARK_STATE:-/var/lib/speech-spark/state}"
VENV="${SPEECH_SPARK_ENGINE_VENV:-/opt/speech-spark/venv-engine}"
STATE="$STATE_DIR/speech-spark-tts-$ROLE.json"
mkdir -p "$STATE_DIR"

state() {  # $1 = status, $2 = message
  jq -n --arg s "$1" --arg e "$2" --arg t "$(date -Is)" '{status: $s, error: $e, time: $t}' >"$STATE"
}
fail() { state error "$1"; echo "ERROR: $1" >&2; exit 1; }

c() { jq -r ".tts.$1" "$CONFIG"; }
SEQS=$(c engine_max_seqs)
MEM0=$(c engine_mem_talker)
MEM1=$(c engine_mem_code2wav)
if [ "$ROLE" = design ]; then MODEL=$(c voicedesign_model); PORT=$(c voicedesign_port)
else MODEL=$(c model); PORT=$(c engine_port); fi

[[ "$MODEL" =~ ^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$ ]] || fail "invalid model id '$MODEL'"
[[ "$PORT" =~ ^[0-9]{4,5}$ ]] || fail "invalid port '$PORT'"
[[ "$SEQS" =~ ^[0-9]{1,3}$ ]] || fail "invalid engine_max_seqs '$SEQS'"
for m in "$MEM0" "$MEM1"; do
  [[ "$m" =~ ^0?\.[0-9]+$ ]] || fail "engine memory shares must be fractions like 0.05, got '$m'"
done
[ -x "$VENV/bin/vllm" ] || fail "vllm-omni is not installed in $VENV; run install.sh"

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

state loading "starting $MODEL, needs ~$need_gib GiB (first start downloads the model)"
overrides=$(jq -cn --argjson m0 "$MEM0" --argjson m1 "$MEM1" --argjson s "$SEQS" \
  '{"0": {gpu_memory_utilization: $m0, max_num_seqs: $s}, "1": {gpu_memory_utilization: $m1, max_num_seqs: $s}}')

exec "$VENV/bin/vllm" serve "$MODEL" --omni \
  --host 127.0.0.1 --port "$PORT" \
  --trust-remote-code \
  --served-model-name "$MODEL" \
  --stage-overrides "$overrides"
