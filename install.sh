#!/usr/bin/env bash
# Speech on DGX Spark: installs Qwen3-ASR + Qwen3-TTS as systemd services with a web
# panel for config, monitoring and updates. Designed to run next to dgx-spark-qwen38.
#
#   sudo ./install.sh                  # install (the first run asks what to install), or update
#   sudo ./install.sh --mode api       # only the models with their APIs, no web panel (or --mode full)
#   sudo ./install.sh --asr 1.7b|0.6b|parakeet|none --tts 0.6b|1.7b|none [--voicedesign]
#   sudo ./install.sh --local          # APIs only on 127.0.0.1 (default --network: reachable in the LAN)
#   sudo ./install.sh --yes            # ask nothing; what is not given stays as before (new: complete)
#   sudo ./install.sh --small          # 0.6B models (least unified memory)
#   sudo ./install.sh --no-tts         # only ASR (or --no-asr)
#   sudo ./install.sh --tts-backend transformers   # TTS without streaming (default: vllm-omni, streams)
#   sudo ./install.sh --asr-backend transformers   # ASR without vLLM (default: vllm, batches and streams)
#   sudo ./install.sh --password XYZ   # panel password (otherwise generated)
#   sudo ./install.sh --no-download    # models download on first start instead
#   sudo ./install.sh --no-smoke       # skip the TTS -> ASR round trip at the end
#   sudo ./install.sh --uninstall      # remove services (keeps models); add --purge for everything
#
# Later updates: the "Update" button in the panel, or  sudo speech-spark update
# Without the panel: sudo speech-spark  (status, info, key, models, update, logs, panel enable)
set -euo pipefail

PREFIX=/opt/speech-spark
ETC=/etc/speech-spark
VAR=/var/lib/speech-spark
SVC_USER=speech
TORCH_INDEX=https://download.pytorch.org/whl/cu130
# Engines: vLLM serves Qwen3-ASR natively; vllm-omni (TTS, streaming) needs the vLLM
# release with the same major/minor.
# Both ship aarch64 wheels on PyPI built for CUDA 13; installed natively, no Docker.
VLLM_VERSION=0.30.0
VLLM_OMNI_VERSION=0.30.0
DEFAULT_REMOTE=https://github.com/db9979/speech-on-dgx-spark
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SMALL=0; WITH_ASR=1; WITH_TTS=1; PASSWORD=""; DOWNLOAD=1; SMOKE=1; FROM_UPDATE=0; TTS_BACKEND=""; ASR_BACKEND=""
MODE=""; ASR_PICK=""; TTS_PICK=""; VD_PICK=""; NET_PICK=""; YES=0; CHOOSE_MODELS=0
while [ $# -gt 0 ]; do
  case "$1" in
    --small) SMALL=1 ;;
    --no-asr) WITH_ASR=0 ;;
    --no-tts) WITH_TTS=0 ;;
    --tts-backend) TTS_BACKEND="$2"; shift ;;
    --asr-backend) ASR_BACKEND="$2"; shift ;;
    --password) PASSWORD="$2"; shift ;;
    --no-download) DOWNLOAD=0 ;;
    --no-smoke) SMOKE=0 ;;
    --mode) MODE="$2"; shift ;;
    --asr) ASR_PICK="$2"; shift ;;
    --tts) TTS_PICK="$2"; shift ;;
    --voicedesign) VD_PICK=yes ;;
    --no-voicedesign) VD_PICK=no ;;
    --local) NET_PICK=local ;;
    --network) NET_PICK=network ;;
    --yes|-y) YES=1 ;;
    --choose-models) CHOOSE_MODELS=1 ;;  # ask the model questions again (sudo speech-spark models)
    --update) FROM_UPDATE=1 ;;  # set by update.sh
    --uninstall) shift; exec "$SRC/uninstall.sh" "$@" ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
case "$TTS_BACKEND" in ""|vllm-omni|transformers) ;; *) echo "--tts-backend must be vllm-omni or transformers" >&2; exit 2 ;; esac
case "$ASR_BACKEND" in ""|vllm|transformers) ;; *) echo "--asr-backend must be vllm or transformers" >&2; exit 2 ;; esac
case "$MODE" in ""|full|api) ;; *) echo "--mode must be full or api" >&2; exit 2 ;; esac
case "$ASR_PICK" in ""|1.7b|0.6b|parakeet|none) ;; *) echo "--asr must be 1.7b, 0.6b, parakeet or none" >&2; exit 2 ;; esac
case "$TTS_PICK" in ""|0.6b|1.7b|none) ;; *) echo "--tts must be 0.6b, 1.7b or none" >&2; exit 2 ;; esac

say()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; progress "$*"; }
# During an update the panel shows a progress bar; each step also goes into this file.
progress() {
  [ -n "${SPEECH_SPARK_PROGRESS:-}" ] || return 0
  local n j; n=$(jq -r '.step // 0' "$SPEECH_SPARK_PROGRESS" 2>/dev/null || echo 0)
  [[ "$n" =~ ^[0-9]{1,4}$ ]] || n=0
  j=$(jq -c --arg t "$1" --argjson n "$((n + 1))" --argjson now "$(date +%s)" '.step=$n | .text=$t | .updated=$now' \
    "$SPEECH_SPARK_PROGRESS" 2>/dev/null) || return 0
  printf '%s\n' "$j" | as_svc tee -- "$SPEECH_SPARK_PROGRESS" >/dev/null 2>&1 || true
}
warn() { printf '\033[1;33mWARN:\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }
# $ETC and $VAR/state belong to the service user, so root never writes or chowns there through a
# link it may have planted: such links (and anything that is not a plain file) are removed first.
no_links() { local f; for f in "$@"; do if [ -L "$f" ] || { [ -e "$f" ] && [ ! -f "$f" ]; }; then rm -rf -- "$f"; fi; done; }
# Between such a check and a write the service user could still put a link there. So root writes a
# file there only by renaming one it made in /etc (root's own folder, same file system; a rename
# replaces the name and never follows a link), and files in $VAR/state as the service user itself.
as_svc() { runuser -u "$SVC_USER" -- "$@"; }
put_file() {  # $1 = file in $ETC, $2 = mode, $3 = owner:group; the content comes from stdin
  local tmp; tmp=$(mktemp "$(dirname "$ETC")/.speech-spark.XXXXXX")
  cat >"$tmp"; chmod "$2" "$tmp"; chown "$3" "$tmp"; mv -fT -- "$tmp" "$1"
}
jqi()  { local j; j=$(jq "$@" "$ETC/config.json") && printf '%s\n' "$j" | put_file "$ETC/config.json" 640 "$SVC_USER:$SVC_USER"; }

[ "$(id -u)" = 0 ] || die "run with sudo"
[ "$(uname -m)" = aarch64 ] || warn "this is $(uname -m), not aarch64; the script targets the DGX Spark"
command -v nvidia-smi >/dev/null || die "nvidia-smi not found; is the NVIDIA driver installed?"
nvidia-smi --query-gpu=name --format=csv,noheader | head -1 | grep -qi gb10 \
  || warn "GPU is not a GB10: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"

# ---------------------------------------------------------------- packages
say "System packages"
export DEBIAN_FRONTEND=noninteractive
# apt may be busy (unattended-upgrades, another apt): wait for its locks up to 10 minutes instead of
# failing at once ("Sperre /var/lib/apt/lists/lock konnte nicht erlangt werden", update V01.0.150)
apt_wait() {
  local i
  for i in $(seq 1 20); do
    apt-get -o DPkg::Lock::Timeout=30 "$@" && return 0
    echo "   apt is busy or failed, trying again in 30 s ($i/20)"
    sleep 30
  done
  return 1
}
PKGS="python3 python3-venv python3-dev build-essential ninja-build git openssl ffmpeg libopus0 sox libsox-fmt-all libsndfile1 curl jq iproute2"
# ninja-build + build-essential: vLLM / FlashInfer compile kernels at first start (JIT)
if ! { apt_wait update -q && apt_wait install -y -q $PKGS; }; then
  # an update only needs packages that the first install already put there
  if [ "$FROM_UPDATE" = 1 ] && dpkg -s $PKGS >/dev/null 2>&1; then
    warn "apt is still busy; all needed packages are already installed, going on without apt"
  else
    die "apt did not finish (another apt is still running?). Try again in a few minutes."
  fi
fi
PY=$(command -v python3)

# ---------------------------------------------------------------- user and dirs
say "Service user and directories"
id "$SVC_USER" >/dev/null 2>&1 || useradd --system --home-dir "$VAR" --shell /usr/sbin/nologin "$SVC_USER"
for g in video render systemd-journal; do getent group "$g" >/dev/null && usermod -aG "$g" "$SVC_USER"; done
install -d -o root -g root -m 755 "$PREFIX"
install -d -o "$SVC_USER" -g "$SVC_USER" -m 750 "$ETC" "$VAR" "$VAR/hf" "$VAR/voices" "$VAR/state"
install -d -o "$SVC_USER" -g "$SVC_USER" -m 700 "$VAR/users"   # profiles and their memory
install -d -o "$SVC_USER" -g "$SVC_USER" -m 700 "$VAR/backups" # daily backups made by the panel
chmod 755 "$VAR"

# ---------------------------------------------------------------- own git clone for updates
# The panel's update button works on $PREFIX/src, independent of where you cloned this repo.
# It is owned by root: the panel can trigger an update but cannot change what gets installed.
if [ "$SRC" != "$PREFIX/src" ]; then
  say "Git clone for updates in $PREFIX/src"
  remote=$DEFAULT_REMOTE; commit=""
  if git -C "$SRC" rev-parse HEAD >/dev/null 2>&1; then
    remote=$(git -C "$SRC" remote get-url origin 2>/dev/null || echo "$DEFAULT_REMOTE")
    commit=$(git -C "$SRC" rev-parse HEAD)
  fi
  if [ ! -d "$PREFIX/src/.git" ]; then
    git clone --quiet --branch main "$remote" "$PREFIX/src" || die "could not clone $remote"
  fi
  git -C "$PREFIX/src" remote set-url origin "$remote"
  git -C "$PREFIX/src" fetch --quiet origin main
  if [ -n "$commit" ] && git -C "$PREFIX/src" cat-file -e "$commit^{commit}" 2>/dev/null; then
    git -C "$PREFIX/src" reset --hard --quiet "$commit"
  else
    [ -n "$commit" ] && warn "your checkout is at a commit that is not on GitHub; updates will follow origin/main"
    git -C "$PREFIX/src" reset --hard --quiet origin/main
  fi
fi
INSTALL_FROM="$SRC"   # the files installed now are the ones next to this script

# ---------------------------------------------------------------- config
# Lanes from dgx-spark-qwen38 that claim most of the unified pool (0.76 / 0.85).
big_lane=""
if systemctl cat qwen38-flash.service >/dev/null 2>&1; then big_lane="qwen38-flash (85 %)"; fi
if systemctl cat qwen38-sglang.service 2>/dev/null | grep -q -- '--mem-fraction-static 0.7'; then big_lane="qwen38-sglang 1M mode (76 %)"; fi

# ---------------------------------------------------------------- what to install
# The first install asks (in a terminal): complete or only the models with their APIs, which
# models, and whether the APIs are reachable from other computers. Later runs and updates keep the
# answers; "sudo speech-spark models" asks the model questions again. The mode lives in $ETC/mode
# (root's file, the panel cannot change it).
FIRST=0; [ -f "$ETC/config.json" ] || FIRST=1
ASK=0; { [ -t 0 ] && [ "$YES" = 0 ] && [ "$FROM_UPDATE" = 0 ]; } && ASK=1
[ "$CHOOSE_MODELS" = 1 ] && [ "$ASK" = 0 ] && die "--choose-models needs a terminal"
OLD_MODE=$(cat "$ETC/mode" 2>/dev/null || true)
case "$OLD_MODE" in full|api) ;; *) OLD_MODE="" ;; esac
ask() {  # $1 = question, $2 = default, rest = allowed answers; prints the answer
  local a ok
  while true; do
    read -r -p "$1 [$2]: " a || die "no answer (no terminal); use --yes or give the options"
    a=${a:-$2}
    for ok in "${@:3}"; do [ "$a" = "$ok" ] && { echo "$a"; return 0; }; done
    echo "   please answer with one of: ${*:3}" >&2
  done
}
gib_free() { awk '/^MemAvailable:/ {printf "%.0f", $2 / 1048576}' /proc/meminfo; }

if [ "$ASK" = 1 ] && [ -z "$MODE" ] && [ -z "$OLD_MODE" ]; then
  echo
  echo "What should be installed?"
  echo "  1) Complete: models + APIs + web panel with the voice assistant"
  echo "  2) Only the models with their APIs, for other services (no web panel)"
  case "$(ask "Choice" 1 1 2)" in 1) MODE=full ;; 2) MODE=api ;; esac
fi
MODE=${MODE:-${OLD_MODE:-full}}

# current choice, as the defaults of the questions
cur_asr() {
  if [ "$FIRST" = 1 ]; then { [ "$SMALL" = 1 ] || [ -n "$big_lane" ]; } && echo 0.6b || echo 1.7b; return; fi
  jq -r 'if .asr.enabled != true then "none" elif .asr.recognizer == "parakeet" then "parakeet"
         elif (.asr.model | test("0.6B")) then "0.6b" else "1.7b" end' "$ETC/config.json"
}
cur_tts() {
  if [ "$FIRST" = 1 ]; then echo 0.6b; return; fi
  jq -r 'if .tts.enabled != true then "none" elif .tts.model == "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice" then "0.6b"
         elif .tts.model == "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice" then "1.7b" else "keep" end' "$ETC/config.json"
}
if [ "$ASK" = 1 ] && { [ "$CHOOSE_MODELS" = 1 ] || { [ "$FIRST" = 1 ] && [ -z "$ASR_PICK$TTS_PICK" ] \
     && [ "$SMALL$WITH_ASR$WITH_TTS" = 011 ]; }; }; then
  echo
  echo "Which models? Memory figures are rough estimates; $(gib_free) GiB are free right now."
  [ -n "$big_lane" ] && echo "(found $big_lane: the 0.6B models are recommended next to it)"
  if [ -z "$ASR_PICK" ]; then
    echo "Speech recognition (ASR, port $(jq -r '.asr.port // 31001' "$ETC/config.json" 2>/dev/null || echo 31001)):"
    echo "  1) Qwen3-ASR 1.7B      most accurate, ~6 GiB"
    echo "  2) Qwen3-ASR 0.6B      ~3 GiB"
    echo "  3) Parakeet            trained on German, runs on the CPU, ~1 GiB"
    echo "  4) none"
    d=$(cur_asr); case "$d" in 1.7b) d=1 ;; 0.6b) d=2 ;; parakeet) d=3 ;; *) d=4 ;; esac
    case "$(ask "Choice" "$d" 1 2 3 4)" in 1) ASR_PICK=1.7b ;; 2) ASR_PICK=0.6b ;; 3) ASR_PICK=parakeet ;; 4) ASR_PICK=none ;; esac
  fi
  if [ -z "$TTS_PICK" ]; then
    echo "Speech output (TTS, port $(jq -r '.tts.port // 31002' "$ETC/config.json" 2>/dev/null || echo 31002)):"
    echo "  1) Qwen3-TTS 0.6B      built-in voices, ~4 GiB"
    echo "  2) Qwen3-TTS 1.7B      also follows style instructions, ~7 GiB"
    echo "  3) none"
    d=$(cur_tts); opts="1 2 3"
    if [ "$d" = keep ]; then
      echo "  4) keep $(jq -r .tts.model "$ETC/config.json")"; opts="1 2 3 4"; d=4
    else
      case "$d" in 0.6b) d=1 ;; 1.7b) d=2 ;; *) d=3 ;; esac
    fi
    # shellcheck disable=SC2086
    case "$(ask "Choice" "$d" $opts)" in 1) TTS_PICK=0.6b ;; 2) TTS_PICK=1.7b ;; 3) TTS_PICK=none ;; 4) TTS_PICK=keep ;; esac
  fi
  if [ "$TTS_PICK" != none ] && [ -z "$VD_PICK" ]; then
    d=n; [ "$FIRST" = 0 ] && [ "$(jq -r .tts.voicedesign_enabled "$ETC/config.json")" = true ] && d=y
    echo "VoiceDesign: design new voices from a description (extra 1.7B model, ~7 GiB)."
    case "$(ask "Install it? (y/n)" "$d" y n j)" in y|j) VD_PICK=yes ;; n) VD_PICK=no ;; esac
  fi
fi
if [ "$ASK" = 1 ] && [ "$FIRST" = 1 ] && [ -z "$NET_PICK" ]; then
  echo
  echo "Should other computers in the network reach the APIs? (An API key is required either way.)"
  echo "  y) yes, on all network interfaces"
  echo "  n) no, only on this machine (127.0.0.1), e.g. behind your own reverse proxy"
  case "$(ask "Choice" y y n j)" in y|j) NET_PICK=network ;; n) NET_PICK=local ;; esac
fi
[ "$ASK" = 1 ] && echo

no_links "$ETC/config.json"
if [ ! -f "$ETC/config.json" ]; then
  say "Writing $ETC/config.json"
  put_file "$ETC/config.json" 640 "$SVC_USER:$SVC_USER" <"$INSTALL_FROM/app/config.default.json"
  if [ "$SMALL" = 1 ] || [ -n "$big_lane" ]; then
    [ -n "$big_lane" ] && [ "$SMALL" = 0 ] && warn "found $big_lane: choosing the 0.6B models so speech fits next to it"
    jqi '.asr.model="Qwen/Qwen3-ASR-0.6B" | .tts.model="Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"'
  fi
  jqi --argjson a "$WITH_ASR" --argjson t "$WITH_TTS" '.asr.enabled=($a==1) | .tts.enabled=($t==1)'
  # Generate an API key; apps send it as "Authorization: Bearer <key>".
  jqi --arg k "sk-$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')" '.api.key=$k'
else
  say "Keeping $ETC/config.json (adding settings introduced by this version)"
  merged=$(jq -s '.[0] * .[1]' "$INSTALL_FROM/app/config.default.json" "$ETC/config.json") \
    && printf '%s\n' "$merged" | put_file "$ETC/config.json" 640 "$SVC_USER:$SVC_USER"
  [ "$SMALL" = 1 ] && jqi '.asr.model="Qwen/Qwen3-ASR-0.6B" | .tts.model="Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"'
fi
[ -n "$TTS_BACKEND" ] && jqi --arg b "$TTS_BACKEND" '.tts.backend=$b'
[ -n "$ASR_BACKEND" ] && jqi --arg b "$ASR_BACKEND" '.asr.backend=$b'
# the answers (or options) from above
case "$ASR_PICK" in
  1.7b) jqi '.asr.enabled=true | .asr.recognizer="qwen" | .asr.model="Qwen/Qwen3-ASR-1.7B"
             | if .asr.engine_mem < 0.055 then .asr.engine_mem=0.06 else . end' ;;
  0.6b) jqi '.asr.enabled=true | .asr.recognizer="qwen" | .asr.model="Qwen/Qwen3-ASR-0.6B"' ;;
  parakeet) jqi '.asr.enabled=true | .asr.recognizer="parakeet"' ;;
  none) jqi '.asr.enabled=false' ;;
esac
case "$TTS_PICK" in
  0.6b) jqi '.tts.enabled=true | .tts.model="Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"' ;;
  1.7b) jqi '.tts.enabled=true | .tts.model="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"' ;;
  none) jqi '.tts.enabled=false' ;;
esac
case "$VD_PICK" in yes) jqi '.tts.voicedesign_enabled=true' ;; no) jqi '.tts.voicedesign_enabled=false' ;; esac
case "$NET_PICK" in
  local) jqi '.asr.host="127.0.0.1" | .tts.host="127.0.0.1"' ;;
  network) jqi '.asr.host="0.0.0.0" | .tts.host="0.0.0.0"' ;;
esac
# api: only the models with their APIs; full: with the web panel
echo "$MODE" | put_file "$ETC/mode" 644 root:root
# Earlier start values were too generous next to a qwen38 lane; move untouched ones down.
case "$(jq -r .asr.engine_mem "$ETC/config.json")" in 0.08|0.05) jqi '.asr.engine_mem=0.045 | .asr.engine_max_seqs=4' ;; esac
# (0.03 + 0.015 left no room for the KV cache on the Spark)
case "$(jq -c '[.tts.engine_mem_talker, .tts.engine_mem_code2wav]' "$ETC/config.json")" in
  "[0.05,0.05]"|"[0.03,0.015]") jqi '.tts.engine_mem_talker=0.04 | .tts.engine_mem_code2wav=0.025 | .tts.engine_max_seqs=2' ;;
esac
# A 2-frame first chunk (0.16 s of audio) ran out before the next 25-frame chunk was ready.
[ "$(jq -r .tts.initial_chunk_frames "$ETC/config.json")" = 2 ] && jqi '.tts.initial_chunk_frames=8'
# 8 frames (the old default) stalled next to a busy qwen38 lane; move to 10 once.
if [ ! -e "$VAR/state/migrated-chunk10" ]; then
  [ "$(jq -r .tts.initial_chunk_frames "$ETC/config.json")" = 8 ] && jqi '.tts.initial_chunk_frames=10'
  as_svc touch "$VAR/state/migrated-chunk10"
fi
[ "$(jq -r .chat.max_tokens "$ETC/config.json")" = 600 ] && jqi '.chat.max_tokens=4096'   # old default cut long answers off
# The first voice-chat prompt gave pompous, overexcited answers; replace it if untouched.
OLD_PROMPT='Du bist ein freundlicher Sprachassistent. Deine Antworten werden vorgelesen: antworte kurz und natürlich in ganzen Sätzen, ohne Listen, Tabellen, Markdown, Code oder Emojis. Antworte in der Sprache, in der du angesprochen wirst.'
if [ "$(jq -r .chat.system_prompt "$ETC/config.json")" = "$OLD_PROMPT" ]; then
  jqi --slurpfile d "$INSTALL_FROM/app/config.default.json" '.chat.system_prompt=$d[0].chat.system_prompt'
fi
# the 0.6B ASR model needs about half the engine share of the 1.7B one
# (0.025 was too small: "No available memory for the cache blocks" on the Spark)
if jq -e '.asr.model | test("0.6B")' "$ETC/config.json" >/dev/null; then
  case "$(jq -r .asr.engine_mem "$ETC/config.json")" in 0.06|0.045|0.025) jqi '.asr.engine_mem=0.035' ;; esac
fi
# ...and the 1.7B one needs more than the 0.045 first guessed: its ~4 GiB of weights plus vLLM's
# working memory left nothing for the cache ("No available memory for the cache blocks").
if jq -e '.asr.model | test("1.7B")' "$ETC/config.json" >/dev/null && [ "$(jq -r .asr.engine_mem "$ETC/config.json")" = 0.045 ]; then
  jqi '.asr.engine_mem=0.06'
fi
# The voice chat in the panel talks to the qwen38 LLM: take its API key from the user who
# installed qwen38. Panel updates run without SUDO_USER, so also look in the other homes.
# A key imported earlier is refreshed when the file changes; a hand-entered key is kept.
qkey=""
# Root reads it, so only a plain file without links on the way (a link could point at any file of
# the system, whose content would then go to the LLM address as "key"), owned by the home's owner.
qkey_ok() {
  local f="$1/.config/qwen38/api-key"
  [ -f "$f" ] && [ -s "$f" ] && [ "$(realpath -e -- "$f" 2>/dev/null)" = "$(realpath -e -- "$1")/.config/qwen38/api-key" ] \
    && [ "$(stat -c %u -- "$f")" = "$(stat -c %u -- "$1")" ] && [ "$(stat -c %s -- "$f")" -le 512 ]
}
for h in "$( [ -n "${SUDO_USER:-}" ] && getent passwd "$SUDO_USER" | cut -d: -f6)" /home/* /root; do
  [ -n "$h" ] && [ -d "$h" ] && qkey_ok "$h" && { qkey="$h/.config/qwen38/api-key"; break; }
done
if [ -n "$qkey" ]; then
  cur="$(jq -r '.chat.llm_key // ""' "$ETC/config.json")"
  from="$(jq -r '.chat.llm_key_from // ""' "$ETC/config.json")"
  new="$(head -c 512 -- "$qkey" | tr -d ' \n\r')"
  [[ "$new" =~ ^[A-Za-z0-9._~+/=-]{8,300}$ ]] || new=""
  if [ -n "$new" ] && { [ -z "$cur" ] || { [ -n "$from" ] && [ "$cur" != "$new" ]; }; }; then
    jqi --arg k "$new" --arg f "$qkey" '.chat.llm_key=$k | .chat.llm_key_from=$f'
    say "Voice chat: using the qwen38 API key from $qkey"
  fi
fi
no_links "$ETC/config.json"
chown -h "$SVC_USER:$SVC_USER" "$ETC/config.json"; as_svc chmod 640 "$ETC/config.json"

cfg() { jq -r "$1" "$ETC/config.json"; }
# Numbers from the config only ever as plain digits: the file belongs to the service user, and bash
# would run a command hidden in a value used in $(( )). Anything else falls back to the default.
cfg_int() { local v; v=$(cfg "$1"); if [[ "$v" =~ ^[0-9]{1,6}$ ]]; then echo "$v"; else echo "$2"; fi; }

# Browsers only allow the microphone on https (or localhost), so the panel also listens on an
# https port with a self-signed certificate for the voice chat.
TLS="$ETC/tls"
if [ "$MODE" = full ] && [ "$(cfg '.panel.https_port // 0')" != 0 ] && [ ! -s "$TLS/cert.pem" ]; then
  say "Creating a self-signed certificate for the panel's https port (needed for the microphone)"
  [ -L "$TLS" ] && rm -f -- "$TLS"
  as_svc mkdir -p "$TLS"
  san="DNS:localhost,DNS:$(hostname),DNS:$(hostname).local,IP:127.0.0.1"
  for ip in $(hostname -I 2>/dev/null); do case "$ip" in *:*) ;; *) san="$san,IP:$ip" ;; esac; done
  # made by the service user in its own folder (root never writes through a link there)
  as_svc openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=$(hostname) speech-spark" \
    -addext "subjectAltName=$san" -keyout "$TLS/key.pem" -out "$TLS/cert.pem" >/dev/null 2>&1 \
    || warn "could not create the certificate; the voice chat then only works on http://localhost"
fi
[ -L "$TLS" ] && rm -f -- "$TLS"
if [ -d "$TLS" ]; then
  chown -R "$SVC_USER:$SVC_USER" "$TLS"   # -R never follows links; an old root-made folder becomes the service user's
  as_svc chmod 700 "$TLS"; as_svc chmod 600 "$TLS"/key.pem 2>/dev/null || true
fi
HTTPS_PORT=$(cfg_int '.panel.https_port // 0' 0)
ASR_PORT=$(cfg_int .asr.port 31001); TTS_PORT=$(cfg_int .tts.port 31002); PANEL_PORT=$(cfg_int .panel.port 31080)
BACKEND=$(cfg .tts.backend); ASR_BACKEND=$(cfg .asr.backend)
[ "$(cfg .tts.enabled)" = true ] || WITH_TTS=0
[ "$(cfg .asr.enabled)" = true ] || WITH_ASR=0

# ---------------------------------------------------------------- ports
say "Checking ports (dgx-spark-qwen38 uses 30000-30099)"
ports="$ASR_PORT $TTS_PORT"
[ "$MODE" = full ] && ports="$ports $PANEL_PORT"
[ "$MODE" = full ] && [ "$HTTPS_PORT" != 0 ] && ports="$ports $HTTPS_PORT"
[ "$BACKEND" = vllm-omni ] && ports="$ports $(cfg_int .tts.engine_port 31012) $(cfg_int .tts.voicedesign_port 31013)"
[ "$ASR_BACKEND" = vllm ] && ports="$ports $(cfg_int .asr.engine_port 31011)"
for p in $ports; do
  owner=$(ss -ltnpH "sport = :$p" 2>/dev/null | head -1)
  [ -n "$owner" ] || continue
  pid=$(grep -oE 'pid=[0-9]+' <<<"$owner" | head -1 | cut -d= -f2)
  user=""
  if [ -n "$pid" ]; then user=$(ps -o user= -p "$pid" | tr -d ' '); fi
  # our own services (including the engines) from a previous install are fine
  if [ "$user" != "$SVC_USER" ]; then
    die "port $p is already in use: $owner. Change it in $ETC/config.json and re-run."
  fi
done

# ---------------------------------------------------------------- python envs
# Packages that are already there are left as they are (no -U): an update only adds what the new
# version needs, so the running services keep the libraries they were started with, and a new
# release somewhere on PyPI cannot break a working install. A version the code needs is written
# here as "name>=x.y"; pip then upgrades just that package.
make_venv() {  # $1 = name, rest = pip packages
  local v="$PREFIX/venv-$1"; shift
  [ -x "$v/bin/python" ] || "$PY" -m venv "$v"
  "$v/bin/pip" install -q pip wheel setuptools
  if [ "$1" = "--torch" ]; then
    shift
    # PyPI's aarch64 torch has no CUDA; the cu130 build supports Blackwell (GB10).
    "$v/bin/pip" install -q torch torchaudio --index-url "$TORCH_INDEX"
    PIP_EXTRA_INDEX_URL="$TORCH_INDEX" "$v/bin/pip" install -q "$@"
  else
    "$v/bin/pip" install -q "$@"   # only PyPI: a second index could hand out a package of the same name
  fi
}

check_cuda() {
  "$PREFIX/venv-$1/bin/python" - <<'EOF' || die "torch in venv-$1 has no CUDA. Re-run; if it persists, see docs/en/technical.md (Troubleshooting)."
import torch
assert torch.version.cuda and torch.cuda.is_available(), "CPU-only torch"
print(f"   torch {torch.__version__}, CUDA {torch.version.cuda}, {torch.cuda.get_device_name(0)}, arch {torch.cuda.get_arch_list()[-3:]}")
EOF
}

USE_ENGINE=0
{ [ "$WITH_TTS" = 1 ] && [ "$BACKEND" = vllm-omni ]; } && USE_ENGINE=1
{ [ "$WITH_ASR" = 1 ] && [ "$ASR_BACKEND" = vllm ]; } && USE_ENGINE=1

if [ "$WITH_ASR" = 1 ] && [ "$ASR_BACKEND" = transformers ]; then
  say "Python env for Qwen3-ASR (transformers backend, several GB of wheels)"
  make_venv asr --torch qwen-asr fastapi "uvicorn[standard]" python-multipart sherpa-onnx
  check_cuda asr
fi
if [ "$WITH_TTS" = 1 ] && [ "$BACKEND" = transformers ]; then
  say "Python env for Qwen3-TTS (transformers backend)"
  make_venv tts --torch qwen-tts fastapi "uvicorn[standard]" python-multipart num2words
  check_cuda tts
fi
say "Python env for the panel and the ASR / TTS front ends"
# sherpa-onnx + huggingface_hub: the Parakeet recognizer (CPU) that asr_proxy.py runs when chosen
# rmscene pins packaging<24 although it only uses packaging.version.Version; resolved together
# with the rest, pip downgraded packaging to 23.2 and broke wheel (packaging>=24), which showed up
# as "pip's dependency resolver ... dependency conflicts" in every update log. So packaging stays
# current and rmscene comes in without its dependencies; the first line repairs venvs from .273-.276.
[ -x "$PREFIX/venv-panel/bin/pip" ] && "$PREFIX/venv-panel/bin/pip" install -q --no-deps "packaging>=24"
make_venv panel fastapi "uvicorn[standard]" python-multipart "httpx[http2]" psutil num2words numpy pypdf icalendar recurring-ical-events cryptography segno sherpa-onnx huggingface_hub "packaging>=24" "pillow==11.3.0" "onnxruntime==1.22.1" "tokenizers==0.22.1" "pypdfium2==4.30.0"   # pictures (images.py), meaning search (docembed.py), scanned pages (documents.py): fixed versions
"$PREFIX/venv-panel/bin/pip" install -q --no-deps "rmscene==0.8.0"   # reMarkable pages (remarkable.py)

# ---------------------------------------------------------------- engines (vLLM + vllm-omni, native)
if [ "$USE_ENGINE" = 1 ]; then
  say "Python env for the engines: vllm $VLLM_VERSION + vllm-omni $VLLM_OMNI_VERSION (large, takes a while the first time)"
  v="$PREFIX/venv-engine"
  [ -x "$v/bin/python" ] || "$PY" -m venv "$v"
  "$v/bin/pip" install -q -U pip uv
  # uv resolves this large dependency set much faster than pip; torch comes from PyPI,
  # whose aarch64 wheels for this vLLM release are CUDA 13 builds.
  # vllm[audio] brings the decoders for webm / mp4 / ogg uploads.
  "$v/bin/uv" pip install -q --python "$v/bin/python" "vllm[audio]==$VLLM_VERSION" "vllm-omni==$VLLM_OMNI_VERSION"
  check_cuda engine
  "$v/bin/vllm" --help >/dev/null 2>&1 || die "vllm in venv-engine does not start; see the output above"
fi

# ---------------------------------------------------------------- models (ASR / transformers TTS)
if [ "$DOWNLOAD" = 1 ]; then
  dl() {
    sudo -u "$SVC_USER" HF_HOME="$VAR/hf" "$PREFIX/venv-$1/bin/python" -c \
      "import sys; from huggingface_hub import snapshot_download; snapshot_download(sys.argv[1])" "$2"
  }
  if [ "$WITH_ASR" = 1 ] && [ "$ASR_BACKEND" = transformers ]; then
    say "Downloading ASR model"
    dl asr "$(cfg .asr.model)"
    [ "$(cfg .asr.timestamps)" = true ] && dl asr "$(cfg .asr.aligner_model)"
  fi
  if [ "$WITH_ASR" = 1 ] && [ "$(cfg '.asr.recognizer // "qwen"')" = parakeet ]; then
    say "Downloading the Parakeet recognizer (~640 MB)"
    asr_venv=panel; [ "$ASR_BACKEND" = transformers ] && asr_venv=asr
    { cat "$INSTALL_FROM/app/parakeet.py"; echo 'download()'; } \
      | sudo -u "$SVC_USER" HF_HOME="$VAR/hf" "$PREFIX/venv-$asr_venv/bin/python" - \
      || warn "Parakeet download failed; the ASR service retries when it starts"
  fi
  # (with Parakeet the engine stays off; it fetches its model itself if Qwen3-ASR is chosen later)
  if [ "$WITH_ASR" = 1 ] && [ "$ASR_BACKEND" = vllm ] && [ "$(cfg '.asr.recognizer // "qwen"')" != parakeet ]; then
    say "Downloading ASR model for the engine"
    dl engine "$(cfg .asr.model)"
  fi
  if [ "$WITH_TTS" = 1 ] && [ "$BACKEND" = transformers ]; then
    say "Downloading TTS model"
    dl tts "$(cfg .tts.model)"
  fi
  if [ "$WITH_TTS" = 1 ] && [ "$BACKEND" = vllm-omni ]; then
    say "Downloading TTS model for the engine"
    dl engine "$(cfg .tts.model)"
    [ "$(cfg .tts.voicedesign_enabled)" = true ] && dl engine "$(cfg .tts.voicedesign_model)"
  fi
fi

# ---------------------------------------------------------------- self-test (before anything goes live)
# The new code against a fake LLM, TTS and Home Assistant in a throw-away folder. In an update a
# failure stops here, while the running version is untouched.
if [ "${SPEECH_SPARK_NO_SELFTEST:-0}" = 1 ]; then
  say "Self-test skipped (putting the previous version back)"
else
say "Self-test of the panel (fake LLM and TTS, nothing real is touched)"
SELFTEST_LOG="$PREFIX/selftest.log"
work=$(mktemp -d); cp -r "$INSTALL_FROM/app" "$work/app"
if (cd "$work/app" && timeout 600 "$PREFIX/venv-panel/bin/python" -W ignore -m unittest discover -s tests -t . >"$SELFTEST_LOG" 2>&1); then
  echo "   $(grep -E '^Ran ' "$SELFTEST_LOG") - all passed"
else
  tail -n 25 "$SELFTEST_LOG"
  rm -rf "$work"
  [ "$FROM_UPDATE" = 1 ] && die "self-test failed (details: $SELFTEST_LOG); the running version stays"
  warn "self-test failed (details: $SELFTEST_LOG); the services are installed anyway"
fi
rm -rf "$work"
fi

# ================================================================ switch to the new version
# Everything above can fail without touching the running services. From here on the
# new code goes live; update.sh sees the mark and puts the previous version back if a later
# step fails.
[ "$FROM_UPDATE" = 1 ] && touch "$PREFIX/.switched"
say "Installing application files"
rm -rf "$PREFIX/app.new"
cp -r "$INSTALL_FROM/app" "$PREFIX/app.new"
chmod -R a+rX "$PREFIX/app.new"
chmod 755 "$PREFIX/app.new/engine.sh"
rm -rf "$PREFIX/app.old"
[ -d "$PREFIX/app" ] && mv "$PREFIX/app" "$PREFIX/app.old"
mv "$PREFIX/app.new" "$PREFIX/app"
rm -rf "$PREFIX/app.old"

# version shown in the panel
if git -C "$PREFIX/src" rev-parse HEAD >/dev/null 2>&1; then
  g() { git -C "$PREFIX/src" log -1 --format="$1"; }
  jq -n --arg c "$(g %H)" --arg s "$(g %h)" --arg d "$(g %cI)" --arg m "$(g %s)" \
    --arg r "$(git -C "$PREFIX/src" remote get-url origin)" --arg e "vllm $VLLM_VERSION, vllm-omni $VLLM_OMNI_VERSION" \
    --arg v "$(head -1 "$PREFIX/app/VERSION" 2>/dev/null)" \
    '{commit: $c, short: $s, date: $d, subject: $m, remote: $r, branch: "main", engine: $e, version: $v}' >"$PREFIX/VERSION.json"
else
  echo '{"commit": null, "subject": "installed without git"}' >"$PREFIX/VERSION.json"
fi
chmod 644 "$PREFIX/VERSION.json"

# measuring script: sudo speech-spark-bench
cat >/usr/local/bin/speech-spark-bench <<EOF
#!/bin/sh
exec $PREFIX/venv-panel/bin/python $PREFIX/app/bench.py "\$@"
EOF
chmod 755 /usr/local/bin/speech-spark-bench
# status, connection details, API key, models, update, logs, panel on/off: sudo speech-spark
cat >/usr/local/bin/speech-spark <<EOF
#!/bin/sh
exec /bin/bash $PREFIX/app/speech-spark.sh "\$@"
EOF
chmod 755 /usr/local/bin/speech-spark

# ---------------------------------------------------------------- password, sudoers
# Only the web panel has a password (mode full); the APIs use the API key.
if [ "$MODE" = full ]; then
  # a password given here replaces one changed in the panel (whose hash would win otherwise)
  [ -n "$PASSWORD" ] && rm -f -- "$VAR/state/panel-password"
  if [ ! -f "$ETC/panel.env" ] || [ -n "$PASSWORD" ]; then
    [ -n "$PASSWORD" ] || PASSWORD=$(head -c 18 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 16)
    printf 'PANEL_PASSWORD=%s\n' "$PASSWORD" | put_file "$ETC/panel.env" 600 "$SVC_USER:$SVC_USER"
  fi
  no_links "$ETC/panel.env"
  chown -h "$SVC_USER:$SVC_USER" "$ETC/panel.env"; as_svc chmod 600 "$ETC/panel.env"
  PASSWORD=$(sed -n 's/^PANEL_PASSWORD=//p' "$ETC/panel.env")
  # changed in the panel since: only its hash is stored, the file above is outdated
  [ -s "$VAR/state/panel-password" ] && PASSWORD="(changed in the panel; reset with sudo ./install.sh --password NEW)"
fi

# The panel may start/stop/restart exactly these units and start the update, nothing else.
{
  printf '%s ALL=(root) NOPASSWD: ' "$SVC_USER"
  first=1
  for u in asr asr-engine tts tts-engine tts-design; do
    for a in start stop restart; do
      [ $first = 1 ] || printf ', '
      printf '/usr/bin/systemctl %s speech-spark-%s' "$a" "$u"; first=0
    done
  done
  printf ', /usr/bin/systemctl start --no-block speech-spark-update, /usr/bin/systemctl stop speech-spark-update\n'
} >/etc/sudoers.d/speech-spark
chmod 440 /etc/sudoers.d/speech-spark
visudo -cf /etc/sudoers.d/speech-spark >/dev/null || die "sudoers file invalid"

# ---------------------------------------------------------------- systemd
say "systemd units"
QWEN38_AFTER="qwen38-sglang.service qwen38-flash.service qwen38-image.service qwen38-video.service qwen38-llamacpp.service"
common_env="Environment=SPEECH_SPARK_CONFIG=$ETC/config.json
Environment=SPEECH_SPARK_VOICES=$VAR/voices
Environment=SPEECH_SPARK_STATE=$VAR/state
Environment=SPEECH_SPARK_USERS=$VAR/users
Environment=PYTHONUNBUFFERED=1"

if [ "$ASR_BACKEND" = vllm ]; then
  asr_exec="$PREFIX/venv-panel/bin/python $PREFIX/app/asr_proxy.py"
  asr_deps="Wants=speech-spark-asr-engine.service"
  # the proxy (and Parakeet on the CPU, about 1-2 GB) runs here, the model is in the engine
  asr_mem="MemoryMax=4G"
else
  asr_exec="$PREFIX/venv-asr/bin/python $PREFIX/app/asr_server.py"
  asr_deps=""
  asr_mem=""
fi
cat >/etc/systemd/system/speech-spark-asr.service <<EOF
[Unit]
Description=Speech on DGX Spark: Qwen3-ASR ($ASR_BACKEND)
# Start after the qwen38 lanes so their static memory fraction is claimed first.
After=network-online.target $QWEN38_AFTER
Wants=network-online.target
$asr_deps

[Service]
LogNamespace=speech-spark
User=$SVC_USER
Group=$SVC_USER
WorkingDirectory=$PREFIX/app
$common_env
Environment=HF_HOME=$VAR/hf
Environment=PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
ExecStart=$asr_exec
Restart=on-failure
RestartSec=10
# Speech first (plaene/vorrang-sprache.md): more CPU and disk share than anything else on the box.
# If unified memory runs out, the panel (900) goes before speech; speech still before an LLM lane or sshd.
OOMScoreAdjust=500
Nice=-5
CPUWeight=1000
IOWeight=1000
PrivateTmp=yes
$asr_mem

[Install]
WantedBy=multi-user.target
EOF

if [ "$BACKEND" = vllm-omni ]; then
  tts_exec="$PREFIX/venv-panel/bin/python $PREFIX/app/tts_proxy.py"
  tts_deps="Wants=speech-spark-tts-engine.service"
  # only the proxy runs here (the model is in the engine): a runaway request ends in a restart of
  # this service instead of taking memory from the LLM lanes
  tts_mem="MemoryMax=3G"
else
  tts_mem=""
  tts_exec="$PREFIX/venv-tts/bin/python $PREFIX/app/tts_server.py"
  tts_deps=""
fi
cat >/etc/systemd/system/speech-spark-tts.service <<EOF
[Unit]
Description=Speech on DGX Spark: Qwen3-TTS ($BACKEND)
After=network-online.target $QWEN38_AFTER
Wants=network-online.target
$tts_deps

[Service]
LogNamespace=speech-spark
User=$SVC_USER
Group=$SVC_USER
WorkingDirectory=$PREFIX/app
$common_env
Environment=HF_HOME=$VAR/hf
Environment=PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
ExecStart=$tts_exec
Restart=on-failure
RestartSec=10
OOMScoreAdjust=500
Nice=-5
CPUWeight=1000
IOWeight=1000
PrivateTmp=yes
$tts_mem

[Install]
WantedBy=multi-user.target
EOF

engine_unit() {  # $1 = unit suffix, $2 = engine.sh role
  cat >"/etc/systemd/system/speech-spark-$1.service" <<EOF
[Unit]
Description=Speech on DGX Spark: vLLM engine ($2)
After=network-online.target $QWEN38_AFTER
Wants=network-online.target

[Service]
LogNamespace=speech-spark
User=$SVC_USER
Group=$SVC_USER
WorkingDirectory=$VAR
$common_env
Environment=SPEECH_SPARK_ENGINE_VENV=$PREFIX/venv-engine
Environment=HF_HOME=$VAR/hf
Environment=HOME=$VAR
ExecStart=$PREFIX/app/engine.sh $2
Restart=on-failure
RestartSec=30
# first start downloads the model and compiles kernels
TimeoutStartSec=infinity
TimeoutStopSec=30
KillMode=control-group
OOMScoreAdjust=500
Nice=-5
CPUWeight=1000
IOWeight=1000

[Install]
WantedBy=multi-user.target
EOF
}
engine_unit tts-engine main
engine_unit tts-design design
engine_unit asr-engine asr

cat >/etc/systemd/system/speech-spark-panel.service <<EOF
[Unit]
Description=Speech on DGX Spark: web panel
After=network-online.target

[Service]
LogNamespace=speech-spark
User=$SVC_USER
Group=$SVC_USER
WorkingDirectory=$PREFIX/app/panel
$common_env
Environment=SPEECH_SPARK_PREFIX=$PREFIX
# the embedding model of the document search (docembed.py) is downloaded here once
Environment=HF_HOME=$VAR/hf
EnvironmentFile=$ETC/panel.env
ExecStart=$PREFIX/venv-panel/bin/python $PREFIX/app/panel/panel.py
Restart=always
RestartSec=5
# a runaway request restarts the panel instead of taking memory from the LLM lanes
MemoryMax=4G
OOMScoreAdjust=900
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF

# Without the panel (mode api) its watchdog runs on its own: restarts a hung ASR / TTS service or
# engine with the same rules (app/panel/health.py).
cat >/etc/systemd/system/speech-spark-watch.service <<EOF
[Unit]
Description=Speech on DGX Spark: watchdog for the APIs (mode without the web panel)
After=network-online.target

[Service]
LogNamespace=speech-spark
User=$SVC_USER
Group=$SVC_USER
WorkingDirectory=$PREFIX/app/panel
$common_env
Environment=SPEECH_SPARK_PREFIX=$PREFIX
ExecStart=$PREFIX/venv-panel/bin/python $PREFIX/app/api_watchdog.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Runs update.sh from the root-owned clone; started by the panel's update button.
cat >/etc/systemd/system/speech-spark-update.service <<EOF
[Unit]
Description=Speech on DGX Spark: update from GitHub
After=network-online.target
Wants=network-online.target

[Service]
LogNamespace=speech-spark
Type=oneshot
ExecStart=$PREFIX/src/update.sh
TimeoutStartSec=2h
EOF
# ---------------------------------------------------------------- logs
# The speech units log into their own journal namespace with a size and age cap, so a chatty
# engine can never fill the disk (and does not push other logs out of the system journal).
LOG_MB=$(cfg_int '.logs.max_mb // 500' 500); LOG_DAYS=$(cfg_int '.logs.keep_days // 14' 14)
cat >/etc/systemd/journald@speech-spark.conf <<EOF
# written by speech-on-dgx-spark install.sh (config: logs.max_mb, logs.keep_days)
[Journal]
Storage=persistent
SystemMaxUse=${LOG_MB}M
SystemMaxFileSize=$(( LOG_MB / 10 > 1 ? LOG_MB / 10 : 1 ))M
MaxRetentionSec=${LOG_DAYS}day
EOF
systemctl restart systemd-journald@speech-spark.service 2>/dev/null || true
systemctl daemon-reload

# ---------------------------------------------------------------- start
say "Starting services"
if [ "$MODE" = full ]; then
  systemctl disable --now speech-spark-watch.service 2>/dev/null || true
  rm -f /etc/systemd/system/speech-spark-watch.service
  systemctl enable speech-spark-panel.service >/dev/null 2>&1
  systemctl restart speech-spark-panel.service
else
  # only the models with their APIs: no web panel (its data in $VAR stays), the watchdog on its own
  systemctl disable --now speech-spark-panel.service 2>/dev/null || true
  rm -f /etc/systemd/system/speech-spark-panel.service
  systemctl enable speech-spark-watch.service >/dev/null 2>&1
  systemctl restart speech-spark-watch.service
fi
systemctl daemon-reload

# an update only restarts an engine when its settings changed: a restart costs a model load
restart_engine() {  # $1 = unit suffix, $2 = settings signature
  local sigfile="$VAR/state/$1.sig"
  set -- "$1" "$2 units-r2"  # bump when the unit files change in a way a running engine must pick up
  systemctl enable "speech-spark-$1.service" >/dev/null 2>&1
  if [ "$FROM_UPDATE" = 0 ] || [ "$(cat "$sigfile" 2>/dev/null)" != "$2" ] \
     || ! systemctl is-active -q "speech-spark-$1.service"; then
    systemctl restart "speech-spark-$1.service"
  fi
  no_links "$sigfile"; rm -f -- "$sigfile"
  printf '%s\n' "$2" | as_svc tee -- "$sigfile" >/dev/null
}

if [ "$WITH_ASR" = 1 ] && [ "$ASR_BACKEND" = vllm ]; then
  # the old transformers ASR keeps its model in memory until it stops; free it before the
  # engine's memory guard looks at what is available
  systemctl stop speech-spark-asr.service 2>/dev/null || true
  restart_engine asr-engine "$VLLM_VERSION $(jq -c '.asr | {model, engine_mem, engine_max_seqs, engine_port}' "$ETC/config.json")"
else
  systemctl disable --now speech-spark-asr-engine.service 2>/dev/null || true
fi
if [ "$WITH_ASR" = 1 ]; then
  systemctl enable speech-spark-asr.service >/dev/null 2>&1; systemctl restart speech-spark-asr.service
else
  systemctl disable --now speech-spark-asr.service 2>/dev/null || true
fi

if [ "$WITH_TTS" = 1 ] && [ "$BACKEND" = vllm-omni ]; then
  restart_engine tts-engine "$VLLM_OMNI_VERSION $(jq -c '.tts | {model, engine_mem_talker, engine_mem_code2wav, engine_max_seqs, engine_max_model_len, engine_port}' "$ETC/config.json")"
  if [ "$(cfg .tts.voicedesign_enabled)" = true ]; then
    systemctl enable speech-spark-tts-design.service >/dev/null 2>&1; systemctl restart speech-spark-tts-design.service
  else
    systemctl disable --now speech-spark-tts-design.service 2>/dev/null || true
  fi
else
  systemctl disable --now speech-spark-tts-engine.service speech-spark-tts-design.service 2>/dev/null || true
fi
if [ "$WITH_TTS" = 1 ]; then
  systemctl enable speech-spark-tts.service >/dev/null 2>&1; systemctl restart speech-spark-tts.service
else
  systemctl disable --now speech-spark-tts.service 2>/dev/null || true
fi

wait_ready() {  # $1 = name, $2 = port, $3 = minutes; the last status stays in st_$1
  local st=""
  for _ in $(seq 1 $(( $3 * 12 ))); do
    st=$(curl -fs "http://127.0.0.1:$2/health" | jq -r .status 2>/dev/null || true)
    printf -v "st_$1" '%s' "$st"
    case "$st" in ready) echo "   $1 ready"; return 0 ;; error|blocked)
      echo "   $1 $st: $(curl -fs "http://127.0.0.1:$2/health" | jq -r .error)"; return 1 ;; esac
    sleep 5
  done
  echo "   $1 not ready after $3 min (status: ${st:-no answer}); see the panel or: journalctl --namespace=speech-spark -u 'speech-spark-*'"; return 1
}
ok_asr=0; ok_tts=0; st_asr=""; st_tts=""
# an update does not wait as long: the services keep starting on their own afterwards
wait_min=30; [ "$FROM_UPDATE" = 1 ] && wait_min=10
if [ "$WITH_ASR" = 1 ]; then wait_ready asr "$ASR_PORT" "$wait_min" && ok_asr=1; fi
# first engine start pulls the model and compiles kernels
if [ "$WITH_TTS" = 1 ]; then wait_ready tts "$TTS_PORT" "$wait_min" && ok_tts=1; fi

KEY=$(cfg .api.key)
auth=(); [ -n "$KEY" ] && auth=(-H "Authorization: Bearer $KEY")
if [ "$SMOKE" = 1 ] && [ "$ok_tts" = 1 ]; then
  say "Smoke test: TTS -> ASR round trip"
  out=$(mktemp --suffix=.wav)
  if curl -fs "${auth[@]}" "http://127.0.0.1:$TTS_PORT/v1/audio/speech" -H 'Content-Type: application/json' \
       -d '{"input":"Hello from the DGX Spark. Speech is up and running.","language":"English","response_format":"wav"}' -o "$out"; then
    echo "   TTS wrote $(stat -c %s "$out") bytes"
  else
    warn "TTS request failed"
  fi
  if [ "$BACKEND" = vllm-omni ]; then
    first=$(curl -fsN "${auth[@]}" "http://127.0.0.1:$TTS_PORT/v1/audio/speech" -H 'Content-Type: application/json' \
      -d '{"input":"Streaming test.","stream":true,"response_format":"pcm"}' -o /dev/null -w '%{time_starttransfer}' || true)
    [ -n "$first" ] && echo "   streaming: first audio after ${first}s"
  fi
  if [ "$ok_asr" = 1 ] && [ -s "$out" ]; then
    curl -fs "${auth[@]}" "http://127.0.0.1:$ASR_PORT/v1/audio/transcriptions" -F "file=@$out" \
      | jq -r '"   ASR heard: \(.text)"' || warn "ASR request failed"
  fi
  rm -f "$out"
fi

# Without the panel nobody checks an update afterwards, so here: TTS speaks a sentence and ASR has
# to understand it. A failure stops the update, and update.sh puts the previous version back.
# Services that are still loading (an engine that restarts) only give a warning.
live_check() {
  local out text share sentence="Heute ist ein schöner Tag, und der Spark spricht wieder."
  out=$(mktemp --suffix=.wav)
  if ! curl -fs --max-time 180 "${auth[@]}" "http://127.0.0.1:$TTS_PORT/v1/audio/speech" -H 'Content-Type: application/json' \
       -d "$(jq -nc --arg t "$sentence" '{input: $t, language: "German", response_format: "wav"}')" -o "$out" \
     || [ "$(stat -c %s "$out")" -lt 8000 ]; then
    echo "   TTS did not speak"; rm -f "$out"; return 1
  fi
  echo "   TTS spoke $(stat -c %s "$out") bytes"
  if [ "$ok_asr" = 1 ]; then
    text=$(curl -fs --max-time 180 "${auth[@]}" "http://127.0.0.1:$ASR_PORT/v1/audio/transcriptions" \
      -F "file=@$out" -F language=German | jq -r '.text // ""') || text=""
    share=$("$PREFIX/venv-panel/bin/python" -c 'import re, sys
w = lambda s: set(re.findall(r"\w+", s.lower()))
a = w(sys.argv[1]); print(int(100 * len(a & w(sys.argv[2])) / len(a)))' "$sentence" "$text")
    echo "   ASR heard: \"$text\" ($share % of the words)"
    [ "$share" -ge 60 ] || { rm -f "$out"; return 1; }
  fi
  rm -f "$out"
}
if [ "$MODE" = api ] && [ "$FROM_UPDATE" = 1 ]; then
  say "Live check: TTS speaks a sentence, ASR has to understand it"
  # a front end that does not answer at all is broken in the new version, not loading
  { [ "$WITH_ASR" = 1 ] && [ -z "$st_asr" ]; } && die "the ASR service does not answer after the update"
  { [ "$WITH_TTS" = 1 ] && [ -z "$st_tts" ]; } && die "the TTS service does not answer after the update"
  if [ "$WITH_TTS" = 1 ] && [ "$ok_tts" = 1 ]; then
    live_check || die "live check failed after the update"
  elif [ "$WITH_TTS" = 1 ]; then
    warn "TTS is not ready yet (${st_tts}); live check skipped"
  else
    echo "   no TTS installed, nothing to speak; the services answer"
  fi
fi

# connection details for other services: printed here, kept in $ETC/connection.txt (root only)
bash "$PREFIX/app/speech-spark.sh" info --save >/dev/null || warn "could not write $ETC/connection.txt"
IP=$(hostname -I | awk '{print $1}')
# An update runs from the panel and its output lands in the journal, which the panel shows: no
# password or key there (sudo speech-spark key prints the key, the password is in $ETC/panel.env).
if [ "$FROM_UPDATE" = 1 ]; then
  PASSWORD="(unchanged; sudo cat $ETC/panel.env)"; KEY="(unchanged; sudo speech-spark key)"
fi
if [ "$MODE" = full ]; then
cat <<EOF

------------------------------------------------------------------
 Panel:     http://$IP:$PANEL_PORT   (opens with the assistant; settings need the password: $PASSWORD)
 Voice chat: https://$IP:$HTTPS_PORT  (panel page "Assistent"; accept the self-signed certificate once)
 ASR API:   http://$IP:$ASR_PORT/v1/audio/transcriptions   (backend: $ASR_BACKEND)
 TTS API:   http://$IP:$TTS_PORT/v1/audio/speech   (backend: $BACKEND)
 API key:   ${KEY:-none}
 Config:    $ETC/config.json     Logs: sudo speech-spark logs
 Update:    panel: Übersicht -> System und Update, or: sudo speech-spark update
 Measure:   panel: Übersicht -> System und Update, or: sudo speech-spark-bench
 Examples for other services: sudo speech-spark info
------------------------------------------------------------------
EOF
else
  echo
  echo "------------------------------------------------------------------"
  if [ "$FROM_UPDATE" = 1 ]; then echo " Connection details and keys: sudo speech-spark info"; else cat "$ETC/connection.txt" 2>/dev/null || true; fi
  echo
  echo " Installed without the web panel. Status: sudo speech-spark status   Update: sudo speech-spark update"
  echo " Add the panel later: sudo speech-spark panel enable"
  echo "------------------------------------------------------------------"
fi
