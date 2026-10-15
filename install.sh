#!/usr/bin/env bash
# Speech on DGX Spark: installs Qwen3-ASR + Qwen3-TTS as systemd services with a web
# panel for config, monitoring and updates. Designed to run next to dgx-spark-qwen38.
#
#   sudo ./install.sh                  # install (the first run asks what to install), or update
#   sudo ./install.sh --mode api       # only the models with their APIs, no web panel (or --mode full)
#   sudo ./install.sh --mode api --teilen   # Spark teilen: only the models, for a panel on another computer (pairing code)
#   sudo ./install.sh --mode panel --modelle HOST  # Spark teilen: only the panel (Raspberry Pi 5), models on HOST
#   sudo ./install.sh --asr 1.7b|0.6b|parakeet|none --tts 0.6b|1.7b|none [--voicedesign]
#   sudo ./install.sh --bild 4b-q8|4b-q4|9b-q8|9b-q4|none   # Bilder malen with FLUX.2 [klein] (optional, default none)
#   sudo ./install.sh --llm [--kolibri]  # vLLM for the own language model (venv-llm; Kolibri-1 needs its own venv)
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
# The own language model (plan eigene-modelle.md, E2) has its own vLLM in venv-llm, apart from vllm-omni's; Kolibri-1
# needs vLLM 0.29 with Aleph Alpha's plugin (pinned by its wheel's SHA-256, installed without its dependencies).
VLLM_LLM_VERSION=0.30.0
VLLM_KOLIBRI_VERSION=0.29.0
KOLIBRI_PLUGIN="aleph-alpha-inference==1.0.0 --hash=sha256:5a0ca118e67924f10c4f9c04dd64bef117007a17dd820233a8841b9cb8d6f211"
DEFAULT_REMOTE=https://github.com/db9979/speech-on-dgx-spark
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SMALL=0; WITH_ASR=1; WITH_TTS=1; PASSWORD=""; DOWNLOAD=1; SMOKE=1; FROM_UPDATE=0; TTS_BACKEND=""; ASR_BACKEND=""
TEILEN_PICK=0; MODELLE_PICK=""; PANEL_PICK=0
MODE=""; ASR_PICK=""; TTS_PICK=""; VD_PICK=""; BILD_PICK=""; NET_PICK=""; YES=0; CHOOSE_MODELS=0; LLM_PICK=0; KOLIBRI_PICK=0
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
    --teilen) TEILEN_PICK=1 ;;            # Spark teilen: the model computer (plan raspberry-split B6b)
    --modelle) MODELLE_PICK="$2"; shift ;;  # Spark teilen: the panel computer, models on this host
    --asr) ASR_PICK="$2"; shift ;;
    --tts) TTS_PICK="$2"; shift ;;
    --voicedesign) VD_PICK=yes ;;
    --no-voicedesign) VD_PICK=no ;;
    --bild) BILD_PICK="$2"; shift ;;
    --llm) LLM_PICK=1 ;;
    --kolibri) LLM_PICK=1; KOLIBRI_PICK=1 ;;
    --local) NET_PICK=local ;;
    --network) NET_PICK=network ;;
    --yes|-y) YES=1 ;;
    --choose-models) CHOOSE_MODELS=1 ;;  # ask the model questions again (sudo speech-spark models)
    --update) FROM_UPDATE=1 ;;  # set by update.sh
    --uninstall) shift; exec "$SRC/uninstall.sh" "$@" ;;
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
case "$TTS_BACKEND" in ""|vllm-omni|transformers) ;; *) echo "--tts-backend must be vllm-omni or transformers" >&2; exit 2 ;; esac
case "$ASR_BACKEND" in ""|vllm|transformers) ;; *) echo "--asr-backend must be vllm or transformers" >&2; exit 2 ;; esac
case "$MODE" in ""|full|api|panel) ;; *) echo "--mode must be full, api or panel" >&2; exit 2 ;; esac
# Spark teilen: "panel" is the complete install without models of its own (they run on --modelle), written as full
[ "$MODE" = panel ] && { MODE=full; PANEL_PICK=1; }
if [ -n "$MODELLE_PICK" ] && ! [[ "$MODELLE_PICK" =~ ^[A-Za-z0-9][A-Za-z0-9.:-]{0,252}$ ]]; then
  echo "--modelle needs the name or IP address of the model computer" >&2; exit 2
fi
[ "$PANEL_PICK" = 1 ] && [ -z "$MODELLE_PICK" ] && { echo "--mode panel needs --modelle <name-or-ip of the model computer>" >&2; exit 2; }
[ -n "$MODELLE_PICK" ] && [ "$TEILEN_PICK" = 1 ] && { echo "--teilen (model computer) and --modelle (panel computer) exclude each other" >&2; exit 2; }
[ "$TEILEN_PICK" = 1 ] && [ "$MODE" = full ] && { echo "--teilen goes with --mode api" >&2; exit 2; }
[ "$TEILEN_PICK" = 1 ] && MODE=api
[ -n "$MODELLE_PICK" ] && MODE=full
case "$ASR_PICK" in ""|1.7b|0.6b|parakeet|none) ;; *) echo "--asr must be 1.7b, 0.6b, parakeet or none" >&2; exit 2 ;; esac
case "$TTS_PICK" in ""|0.6b|1.7b|none) ;; *) echo "--tts must be 0.6b, 1.7b or none" >&2; exit 2 ;; esac
case "$BILD_PICK" in ""|4b-q8|4b-q4|9b-q8|9b-q4|none) ;; *) echo "--bild must be 4b-q8, 4b-q4, 9b-q8, 9b-q4 or none" >&2; exit 2 ;; esac

say()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; progress "$*"; }
# During an update the panel shows a progress bar; each step also goes into this file.
progress() {
  [ -n "${SPEECH_SPARK_PROGRESS:-}" ] || return 0
  # the file lies in the service user's state folder: read as that user (never through a planted link)
  local n j c; c=$(as_svc cat -- "$SPEECH_SPARK_PROGRESS" 2>/dev/null) || return 0
  n=$(printf '%s\n' "$c" | jq -r '.step // 0' 2>/dev/null || echo 0)
  [[ "$n" =~ ^[0-9]{1,4}$ ]] || n=0
  j=$(printf '%s\n' "$c" | jq -c --arg t "$1" --argjson n "$((n + 1))" --argjson now "$(date +%s)" \
    '.step=$n | .text=$t | .updated=$now' 2>/dev/null) || return 0
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
# $ETC belongs to the service user too: root reads config.json only as that user, so a link planted there
# never makes root read one of its own files (and write it back as config.json)
cfg_json() { as_svc cat -- "$ETC/config.json"; }
cfgq() { cfg_json | jq "$@"; }
jqi()  { local j; j=$(cfg_json | jq "$@") && [ -n "$j" ] && printf '%s\n' "$j" | put_file "$ETC/config.json" 640 "$SVC_USER:$SVC_USER"; }

[ "$(id -u)" = 0 ] || die "run with sudo"
[ "$(uname -m)" = aarch64 ] || warn "this is $(uname -m), not aarch64; the script targets the DGX Spark"
# Spark teilen: the panel computer (--modelle, or models.host on another computer from an earlier pairing, as in every
# update there) needs no GPU; only the computer with the models does
gpu_needed=1
[ -n "$MODELLE_PICK" ] && gpu_needed=0
[ -f "$ETC/config.json" ] && [ "$(cfg_json 2>/dev/null \
  | jq -r '(.models.host // "127.0.0.1") | . == "127.0.0.1" or . == "localhost" or . == "::1"' 2>/dev/null)" = false ] && gpu_needed=0
if [ "$gpu_needed" = 1 ]; then
  command -v nvidia-smi >/dev/null || die "nvidia-smi not found; is the NVIDIA driver installed? (panel on another computer: --mode panel --modelle <dgx>)"
  nvidia-smi --query-gpu=name --format=csv,noheader | head -1 | grep -qi gb10 \
    || warn "GPU is not a GB10: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
fi

# Spark teilen: the panel computer (Raspberry Pi 5 or another) needs a 64-bit system and Python 3.11 or newer; the
# panel's environment is built from the lock file, which the self-test covers for 3.11 to 3.13
if [ -n "$MODELLE_PICK" ]; then
  case "$(uname -m)" in aarch64|x86_64) ;; *) die "the panel computer needs a 64-bit system (e.g. Raspberry Pi OS Lite 64-bit)" ;; esac
  python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null || die "the panel computer needs Python 3.11 or newer"
fi

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
# Spark teilen: the model computer's firewall for the door (teilen.py regeln)
{ [ "$TEILEN_PICK" = 1 ] || [ -f "$ETC/teilen" ]; } && PKGS="$PKGS nftables"
# ninja-build + build-essential: vLLM / FlashInfer compile kernels at first start (JIT)
# An update leaves apt alone when every package is there already (security updates come from the
# system's own unattended-upgrades): apt update costs CPU and time while somebody may be talking.
if [ "$FROM_UPDATE" = 1 ] && dpkg -s $PKGS >/dev/null 2>&1; then
  echo "   all packages are installed, apt skipped"
elif ! { apt_wait update -q && apt_wait install -y -q $PKGS; }; then
  # an update only needs packages that the first install already put there
  if [ "$FROM_UPDATE" = 1 ] && dpkg -s $PKGS >/dev/null 2>&1; then
    warn "apt is still busy; all needed packages are already installed, going on without apt"
  else
    die "apt did not finish (another apt is still running?). Try again in a few minutes."
  fi
fi
# Anrufe von unterwegs (app/panel/anrufe.py): coturn as the Vermittler, run only by its own unit below and only
# while the admin switch is on. The distribution's coturn.service is masked before installing, so it never starts
# with its defaults; missing coturn only means calls stay at home (never stops an update).
if [ "$MODE" = full ]; then
  # mask --now: also stops one that already runs (coturn installed by hand before the mask: it holds port 3478)
  systemctl mask --now coturn.service >/dev/null 2>&1 || true
  if ! command -v turnserver >/dev/null 2>&1; then
    # an update skips "apt update" above, so the package lists may be too old to know coturn: fresh lists first
    { apt-get -o DPkg::Lock::Timeout=120 update -q && \
      apt-get -o DPkg::Lock::Timeout=120 install -y -q --no-install-recommends coturn; } \
      || warn "coturn not installed: calls only work at home for now (sudo apt install coturn, then sudo speech-spark update)"
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
# Spark teilen (plan raspberry-split B6b): the model computer of a split install keeps the door, the Wärter and the
# firewall in every update ($ETC/teilen, like $ETC/mode root's file); the complete install never has them
TEILEN=0
{ [ "$TEILEN_PICK" = 1 ] || { [ -f "$ETC/teilen" ] && [ ! -L "$ETC/teilen" ]; }; } && [ "$MODE" = api ] && TEILEN=1

# current choice, as the defaults of the questions
cur_asr() {
  if [ "$FIRST" = 1 ]; then { [ "$SMALL" = 1 ] || [ -n "$big_lane" ]; } && echo 0.6b || echo 1.7b; return; fi
  cfgq -r 'if .asr.enabled != true then "none" elif .asr.recognizer == "parakeet" then "parakeet"
         elif (.asr.model | test("0.6B")) then "0.6b" else "1.7b" end'
}
cur_tts() {
  if [ "$FIRST" = 1 ]; then echo 0.6b; return; fi
  cfgq -r 'if .tts.enabled != true then "none" elif .tts.model == "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice" then "0.6b"
         elif .tts.model == "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice" then "1.7b" else "keep" end'
}
# One model question: the lines and their keys come from the model catalog (app/modelle.py wahl), then "none"
# (and "keep" for a model chosen by hand). pick_model <art> <current key> [kept model]; the answer lands in PICKED.
pick_model() {
  local art=$1 cur=$2 keep=${3:-} keys=() opts=() i d
  read -r -a keys <<<"$(python3 "$INSTALL_FROM/app/modelle.py" wahl-keys "$art")"
  python3 "$INSTALL_FROM/app/modelle.py" wahl "$art"
  keys+=(none); echo "  ${#keys[@]}) none"
  if [ -n "$keep" ]; then keys+=(keep); echo "  ${#keys[@]}) keep $keep"; fi
  d=${#keys[@]}   # none, or keep when a model was chosen by hand
  for i in "${!keys[@]}"; do opts+=($((i + 1))); [ "${keys[$i]}" = "$cur" ] && d=$((i + 1)); done
  i=$(ask "Choice" "$d" "${opts[@]}")
  PICKED=${keys[$((i - 1))]}
}
[ "$CHOOSE_MODELS" = 1 ] && [ -n "$MODELLE_PICK" ] && die "the models are chosen on the model computer (sudo speech-spark models there)"
if [ "$ASK" = 1 ] && [ -z "$MODELLE_PICK" ] && { [ "$CHOOSE_MODELS" = 1 ] || { [ "$FIRST" = 1 ] && [ -z "$ASR_PICK$TTS_PICK" ] \
     && [ "$SMALL$WITH_ASR$WITH_TTS" = 011 ]; }; }; then
  echo
  echo "Which models? Memory figures are rough estimates; $(gib_free) GiB are free right now."
  [ -n "$big_lane" ] && echo "(found $big_lane: the 0.6B models are recommended next to it)"
  if [ -z "$ASR_PICK" ]; then
    echo "Speech recognition (ASR, port $(cfgq -r '.asr.port // 31001' 2>/dev/null || echo 31001)):"
    pick_model asr "$(cur_asr)"; ASR_PICK=$PICKED
  fi
  if [ -z "$TTS_PICK" ]; then
    echo "Speech output (TTS, port $(cfgq -r '.tts.port // 31002' 2>/dev/null || echo 31002)):"
    d=$(cur_tts)
    if [ "$d" = keep ]; then pick_model tts keep "$(cfgq -r .tts.model)"; else pick_model tts "$d"; fi
    TTS_PICK=$PICKED
  fi
  if [ "$TTS_PICK" != none ] && [ -z "$VD_PICK" ]; then
    d=n; [ "$FIRST" = 0 ] && [ "$(cfgq -r .tts.voicedesign_enabled)" = true ] && d=y
    echo "VoiceDesign: design new voices from a description (extra 1.7B model, ~$(python3 "$INSTALL_FROM/app/modelle.py" gib qwen3-tts-1.7b-voicedesign) GiB)."
    case "$(ask "Install it? (y/n)" "$d" y n j)" in y|j) VD_PICK=yes ;; n) VD_PICK=no ;; esac
  fi
fi
# Bilder malen (plan bildgenerierung): only with the panel, it is the only caller (on a split install the model
# computer paints for the panel on the other computer); off unless asked for
if [ "$ASK" = 1 ] && { { [ "$MODE" = full ] && [ -z "$MODELLE_PICK" ]; } || [ "$TEILEN" = 1 ]; } && { [ "$FIRST" = 1 ] || [ "$CHOOSE_MODELS" = 1 ]; } && [ -z "$BILD_PICK" ]; then
  echo
  echo "Bilder malen: the Spark paints pictures itself with FLUX.2 [klein] (loaded only while painting)."
  echo "  ($(gib_free) GiB are free right now.)"
  d=none; [ "$FIRST" = 0 ] && [ "$(cfgq -r '.image.enabled // false')" = true ] && d=4b-q8
  pick_model bild "$d"; BILD_PICK=$PICKED
fi
if [ "$ASK" = 1 ] && [ "$FIRST" = 1 ] && [ -z "$NET_PICK" ] && [ "$TEILEN" = 0 ] && [ -z "$MODELLE_PICK" ]; then
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
  merged=$(cfg_json | jq -s '.[0] * .[1]' "$INSTALL_FROM/app/config.default.json" -) \
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
case "$BILD_PICK" in
  none) jqi '.image.enabled=false' ;;
  ?*) jqi --arg v "$BILD_PICK" '.image.enabled=true | .image.variant=$v' ;;
esac
case "$NET_PICK" in
  local) jqi '.asr.host="127.0.0.1" | .tts.host="127.0.0.1"' ;;
  network) jqi '.asr.host="0.0.0.0" | .tts.host="0.0.0.0"' ;;
esac
# Spark teilen: on the model computer the services listen only on 127.0.0.1; the door (tlstor.py) takes the same
# ports on the network address, with TLS and only for the panel computer
[ "$TEILEN" = 1 ] && jqi '.asr.host="127.0.0.1" | .tts.host="127.0.0.1" | .llm.host="127.0.0.1"'
# an old configuration that never went through the panel's check (admin.validate): speech APIs that listen in
# the network get a key; without one the services answer only this machine itself (common.api_key_dependency)
if [ -z "$(cfgq -r '.api.key // ""')" ] \
   && [ "$(cfgq -r '[.asr.host, .tts.host] | all(. == "127.0.0.1" or . == "::1" or . == "localhost")')" != true ]; then
  warn "the speech APIs listen in the network without an API key: a new key is set (Einstellungen -> API-Schlüssel)"
  jqi --arg k "sk-$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')" '.api.key=$k'
fi
# api: only the models with their APIs; full: with the web panel
echo "$MODE" | put_file "$ETC/mode" 644 root:root
if [ "$TEILEN" = 1 ]; then echo 1 | put_file "$ETC/teilen" 644 root:root; else no_links "$ETC/teilen"; rm -f -- "$ETC/teilen"; fi
# Earlier start values were too generous next to a qwen38 lane; move untouched ones down.
case "$(cfgq -r .asr.engine_mem)" in 0.08|0.05) jqi '.asr.engine_mem=0.045 | .asr.engine_max_seqs=4' ;; esac
# (0.03 + 0.015 left no room for the KV cache on the Spark)
case "$(cfgq -c '[.tts.engine_mem_talker, .tts.engine_mem_code2wav]')" in
  "[0.05,0.05]"|"[0.03,0.015]") jqi '.tts.engine_mem_talker=0.04 | .tts.engine_mem_code2wav=0.025 | .tts.engine_max_seqs=2' ;;
esac
# A 2-frame first chunk (0.16 s of audio) ran out before the next 25-frame chunk was ready.
[ "$(cfgq -r .tts.initial_chunk_frames)" = 2 ] && jqi '.tts.initial_chunk_frames=8'
# 8 frames (the old default) stalled next to a busy qwen38 lane; move to 10 once.
if [ ! -e "$VAR/state/migrated-chunk10" ]; then
  [ "$(cfgq -r .tts.initial_chunk_frames)" = 8 ] && jqi '.tts.initial_chunk_frames=10'
  as_svc touch "$VAR/state/migrated-chunk10"
fi
[ "$(cfgq -r .chat.max_tokens)" = 600 ] && jqi '.chat.max_tokens=4096'   # old default cut long answers off
# The first voice-chat prompt gave pompous, overexcited answers; replace it if untouched.
OLD_PROMPT='Du bist ein freundlicher Sprachassistent. Deine Antworten werden vorgelesen: antworte kurz und natürlich in ganzen Sätzen, ohne Listen, Tabellen, Markdown, Code oder Emojis. Antworte in der Sprache, in der du angesprochen wirst.'
if [ "$(cfgq -r .chat.system_prompt)" = "$OLD_PROMPT" ]; then
  jqi --slurpfile d "$INSTALL_FROM/app/config.default.json" '.chat.system_prompt=$d[0].chat.system_prompt'
fi
# the 0.6B ASR model needs about half the engine share of the 1.7B one
# (0.025 was too small: "No available memory for the cache blocks" on the Spark)
if cfgq -e '.asr.model | test("0.6B")' >/dev/null; then
  case "$(cfgq -r .asr.engine_mem)" in 0.06|0.045|0.025) jqi '.asr.engine_mem=0.035' ;; esac
fi
# ...and the 1.7B one needs more than the 0.045 first guessed: its ~4 GiB of weights plus vLLM's
# working memory left nothing for the cache ("No available memory for the cache blocks").
if cfgq -e '.asr.model | test("1.7B")' >/dev/null && [ "$(cfgq -r .asr.engine_mem)" = 0.045 ]; then
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
# after the move to the own language model (llm.enabled) the chat talks to the LLM-Tor with api.key: no qwen38 key
[ "$(cfgq -r '.llm.enabled // false')" = true ] && qkey=""
if [ -n "$qkey" ]; then
  cur="$(cfgq -r '.chat.llm_key // ""')"
  from="$(cfgq -r '.chat.llm_key_from // ""')"
  new="$(head -c 512 -- "$qkey" | tr -d ' \n\r')"
  [[ "$new" =~ ^[A-Za-z0-9._~+/=-]{8,300}$ ]] || new=""
  if [ -n "$new" ] && { [ -z "$cur" ] || { [ -n "$from" ] && [ "$cur" != "$new" ]; }; }; then
    jqi --arg k "$new" --arg f "$qkey" '.chat.llm_key=$k | .chat.llm_key_from=$f'
    say "Voice chat: using the qwen38 API key from $qkey"
  fi
fi
no_links "$ETC/config.json"
chown -h "$SVC_USER:$SVC_USER" "$ETC/config.json"; as_svc chmod 640 "$ETC/config.json"

cfg() { cfgq -r "$1"; }
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
  as_svc chmod 700 "$TLS"; as_svc chmod 600 "$TLS"/key.pem "$TLS"/tor-key.pem 2>/dev/null || true
fi
HTTPS_PORT=$(cfg_int '.panel.https_port // 0' 0)
ASR_PORT=$(cfg_int .asr.port 31001); TTS_PORT=$(cfg_int .tts.port 31002); PANEL_PORT=$(cfg_int .panel.port 31080)
BACKEND=$(cfg .tts.backend); ASR_BACKEND=$(cfg .asr.backend)
[ "$(cfg .tts.enabled)" = true ] || WITH_TTS=0
[ "$(cfg .asr.enabled)" = true ] || WITH_ASR=0
WITH_BILD=0; { [ "$MODE" = full ] || [ "$TEILEN" = 1 ]; } && [ "$(cfg '.image.enabled // false')" = true ] && WITH_BILD=1
# venv-llm / venv-kolibri: once installed, every update keeps them current; the services run only with llm.enabled
WITH_LLM=$LLM_PICK; [ -x "$PREFIX/venv-llm/bin/vllm" ] && WITH_LLM=1
WITH_KOLIBRI=$KOLIBRI_PICK; [ -x "$PREFIX/venv-kolibri/bin/vllm" ] && WITH_KOLIBRI=1
LLM_ON=0; [ "$WITH_LLM" = 1 ] && [ "$(cfg '.llm.enabled // false')" = true ] && LLM_ON=1
# Spark teilen: the panel computer (models.host on another computer, set by the pairing) installs no model, engine or
# model service of its own; its pages read what runs from the model computer
PANEL_ONLY=0
if [ "$MODE" = full ] && { [ -n "$MODELLE_PICK" ] \
     || [ "$(cfg '(.models.host // "127.0.0.1") | . == "127.0.0.1" or . == "localhost" or . == "::1"')" != true ]; }; then
  PANEL_ONLY=1; WITH_ASR=0; WITH_TTS=0; WITH_BILD=0; WITH_LLM=0; WITH_KOLIBRI=0; LLM_ON=0; DOWNLOAD=0; SMOKE=0
fi

# ---------------------------------------------------------------- ports
say "Checking ports (dgx-spark-qwen38 uses 30000-30099)"
ports=""
[ "$PANEL_ONLY" = 0 ] && ports="$ASR_PORT $TTS_PORT"
[ "$MODE" = full ] && ports="$ports $PANEL_PORT"
[ "$MODE" = full ] && [ "$HTTPS_PORT" != 0 ] && ports="$ports $HTTPS_PORT"
[ "$WITH_TTS" = 1 ] && [ "$BACKEND" = vllm-omni ] && ports="$ports $(cfg_int .tts.engine_port 31012) $(cfg_int .tts.voicedesign_port 31013)"
[ "$WITH_ASR" = 1 ] && [ "$ASR_BACKEND" = vllm ] && ports="$ports $(cfg_int .asr.engine_port 31011)"
[ "$TEILEN" = 1 ] && ports="$ports 31007"   # the Wärter (common.WAERTER_PORT); the door shares the services' ports
[ "$WITH_BILD" = 1 ] && ports="$ports $(cfg_int .image.port 31005) $(cfg_int .image.engine_port 31015)"
[ "$LLM_ON" = 1 ] && ports="$ports $(cfg_int .llm.port 31006) $(cfg_int .llm.engine_port 31016) $(cfg_int .llm.sehen_port 31017)"
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
# An update asks pip only when the package list of an environment changed: $v/.pkgs keeps the list
# the last successful run installed (root's file in root's folder).
same_pkgs() {  # $1 = venv folder, $2 = package list; true when an update finds nothing new to install
  [ "$FROM_UPDATE" = 1 ] && [ -x "$1/bin/python" ] && [ -f "$1/.pkgs" ] && [ ! -L "$1/.pkgs" ] \
    && [ "$(cat "$1/.pkgs")" = "$2" ]
}
make_venv() {  # $1 = name, rest = pip packages
  local v="$PREFIX/venv-$1" sig="pkgs-r1 $*"; shift
  if same_pkgs "$v" "$sig"; then echo "   venv-${v##*/venv-}: packages unchanged, pip skipped"; return 0; fi
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
  rm -f -- "$v/.pkgs"; printf '%s\n' "$sig" >"$v/.pkgs"
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
  same_pkgs "$PREFIX/venv-asr" "pkgs-r1 asr --torch qwen-asr fastapi uvicorn[standard] python-multipart sherpa-onnx" && asr_same=1 || asr_same=0
  make_venv asr --torch qwen-asr fastapi "uvicorn[standard]" python-multipart sherpa-onnx
  [ "$asr_same" = 1 ] || check_cuda asr
fi
if [ "$WITH_TTS" = 1 ] && [ "$BACKEND" = transformers ]; then
  say "Python env for Qwen3-TTS (transformers backend)"
  same_pkgs "$PREFIX/venv-tts" "pkgs-r1 tts --torch qwen-tts fastapi uvicorn[standard] python-multipart num2words" && tts_same=1 || tts_same=0
  make_venv tts --torch qwen-tts fastapi "uvicorn[standard]" python-multipart num2words
  [ "$tts_same" = 1 ] || check_cuda tts
fi
say "Python env for the panel and the ASR / TTS front ends"
# sherpa-onnx + huggingface_hub: the Parakeet recognizer (CPU) that asr_proxy.py runs when chosen
# A new environment is built from app/requirements-panel.lock: exactly those versions, each file checked against
# its hash (pip --require-hashes), the same file the GitHub test installs (V01.0.286). The lock already holds every
# dependency, so pip installs it with --no-deps: rmscene's packaging<24 pin (it only uses packaging.version.Version)
# is overridden there, packaging stays current (requirements-panel.override). An environment made before keeps its
# packages as they are (see below) until it is built again (remove $PREFIX/venv-panel, run install.sh).
PANEL_LOCK="$INSTALL_FROM/app/requirements-panel.lock"
if [ -f "$PANEL_LOCK" ] && { [ ! -x "$PREFIX/venv-panel/bin/python" ] || [ -f "$PREFIX/venv-panel/.locked" ]; }; then
  # .locked holds the SHA-256 of the lock file it was built from: an update with the same lock skips pip
  lock_sum=$(sha256sum "$PANEL_LOCK" | cut -c1-64)
  if [ "$FROM_UPDATE" = 1 ] && [ -x "$PREFIX/venv-panel/bin/python" ] && [ ! -L "$PREFIX/venv-panel/.locked" ] \
     && [ "$(cat "$PREFIX/venv-panel/.locked" 2>/dev/null)" = "$lock_sum" ]; then
    echo "   venv-panel: lock file unchanged, pip skipped"
  else
    [ -x "$PREFIX/venv-panel/bin/python" ] || "$PY" -m venv "$PREFIX/venv-panel"
    "$PREFIX/venv-panel/bin/pip" install -q --no-deps --require-hashes -r "$PANEL_LOCK"
  fi
  rm -f -- "$PREFIX/venv-panel/.locked"; printf '%s\n' "$lock_sum" >"$PREFIX/venv-panel/.locked"
else
  # rmscene pins packaging<24 although it only uses packaging.version.Version; resolved together
  # with the rest, pip downgraded packaging to 23.2 and broke wheel (packaging>=24), which showed up
  # as "pip's dependency resolver ... dependency conflicts" in every update log. So packaging stays
  # current and rmscene comes in without its dependencies; the first line repairs venvs from .273-.276.
  if same_pkgs "$PREFIX/venv-panel" "pkgs-r1 legacy-r1"; then
    echo "   venv-panel: packages unchanged, pip skipped"
  else
  [ -x "$PREFIX/venv-panel/bin/pip" ] && "$PREFIX/venv-panel/bin/pip" install -q --no-deps "packaging>=24"
  make_venv panel fastapi "uvicorn[standard]" python-multipart "httpx[http2]" psutil num2words numpy pypdf icalendar recurring-ical-events cryptography segno sherpa-onnx huggingface_hub "packaging>=24" "pillow==11.3.0" "onnxruntime==1.22.1" "tokenizers==0.22.1" "pypdfium2==4.30.0"   # pictures (images.py), meaning search (docembed.py), scanned pages (documents.py): fixed versions
  "$PREFIX/venv-panel/bin/pip" install -q --no-deps "rmscene==0.8.0"   # reMarkable pages (remarkable.py)
  # passkeys (passkey.py): python-fido2 only needs cryptography (above); alone, so its cap on cryptography moves nothing
  "$PREFIX/venv-panel/bin/pip" install -q --no-deps "fido2==2.2.1"
  # bump legacy-r1 when a package in this branch changes
  rm -f -- "$PREFIX/venv-panel/.pkgs"; printf '%s\n' "pkgs-r1 legacy-r1" >"$PREFIX/venv-panel/.pkgs"
  fi
  # Dokumente erstellen (docmake.py): Word, PowerPoint, Excel and PDF packages for an environment made before the lock
  # file, exactly the versions and hashes of requirements-docmake.lock (the same as in requirements-panel.lock),
  # once per version of that file (.docmake holds its SHA-256)
  DOC_LOCK="$INSTALL_FROM/app/requirements-docmake.lock"
  if [ -f "$DOC_LOCK" ]; then
    doc_sum=$(sha256sum "$DOC_LOCK" | cut -c1-64)
    if [ ! -L "$PREFIX/venv-panel/.docmake" ] && [ "$(cat "$PREFIX/venv-panel/.docmake" 2>/dev/null)" = "$doc_sum" ]; then
      echo "   venv-panel: document packages unchanged, pip skipped"
    else
      "$PREFIX/venv-panel/bin/pip" install -q --no-deps --require-hashes -r "$DOC_LOCK"
      rm -f -- "$PREFIX/venv-panel/.docmake"; printf '%s\n' "$doc_sum" >"$PREFIX/venv-panel/.docmake"
    fi
  fi
  # Eigener Speicher (speicher.py): SFTP and SMB3 packages for an environment made before the lock file, exactly the
  # versions and hashes of requirements-speicher.lock (the same as in requirements-panel.lock), once per version of it
  STORE_LOCK="$INSTALL_FROM/app/requirements-speicher.lock"
  if [ -f "$STORE_LOCK" ]; then
    store_sum=$(sha256sum "$STORE_LOCK" | cut -c1-64)
    if [ ! -L "$PREFIX/venv-panel/.speicher" ] && [ "$(cat "$PREFIX/venv-panel/.speicher" 2>/dev/null)" = "$store_sum" ]; then
      echo "   venv-panel: storage packages unchanged, pip skipped"
    else
      "$PREFIX/venv-panel/bin/pip" install -q --no-deps --require-hashes -r "$STORE_LOCK"
      rm -f -- "$PREFIX/venv-panel/.speicher"; printf '%s\n' "$store_sum" >"$PREFIX/venv-panel/.speicher"
    fi
  fi
fi

# ---------------------------------------------------------------- engines (vLLM + vllm-omni, native)
if [ "$USE_ENGINE" = 1 ]; then
  say "Python env for the engines: vllm $VLLM_VERSION + vllm-omni $VLLM_OMNI_VERSION (large, takes a while the first time)"
  v="$PREFIX/venv-engine"
  if same_pkgs "$v" "engine $VLLM_VERSION $VLLM_OMNI_VERSION"; then
    echo "   venv-engine: same versions, nothing to install"
  else
  [ -x "$v/bin/python" ] || "$PY" -m venv "$v"
  "$v/bin/pip" install -q -U pip uv
  # uv resolves this large dependency set much faster than pip; torch comes from PyPI,
  # whose aarch64 wheels for this vLLM release are CUDA 13 builds.
  # vllm[audio] brings the decoders for webm / mp4 / ogg uploads.
  "$v/bin/uv" pip install -q --python "$v/bin/python" "vllm[audio]==$VLLM_VERSION" "vllm-omni==$VLLM_OMNI_VERSION"
  check_cuda engine
  "$v/bin/vllm" --help >/dev/null 2>&1 || die "vllm in venv-engine does not start; see the output above"
  rm -f -- "$v/.pkgs"; printf '%s\n' "engine $VLLM_VERSION $VLLM_OMNI_VERSION" >"$v/.pkgs"
  fi
fi

# ---------------------------------------------------------------- the own language model (optional, plan eigene-modelle)
llm_venv() {  # $1 = name (llm, kolibri), $2 = vLLM version, rest = the plugin's requirement line with its hash
  local v="$PREFIX/venv-$1" ver="$2" sig; shift 2
  sig="llm-r1 $ver $*"
  if same_pkgs "$v" "$sig"; then echo "   venv-${v##*/venv-}: same versions, nothing to install"; return 0; fi
  say "Python env for the own language model: venv-${v##*/venv-} with vllm $ver (large, takes a while the first time)"
  [ -x "$v/bin/python" ] || "$PY" -m venv "$v"
  "$v/bin/pip" install -q -U pip uv
  "$v/bin/uv" pip install -q --python "$v/bin/python" "vllm==$ver"
  if [ $# -gt 0 ]; then
    # the plugin alone, by its hash and without dependencies: vLLM, torch and transformers stay as vLLM brought them
    rm -f -- "$v/.plugin-req"; printf '%s\n' "$*" >"$v/.plugin-req"
    "$v/bin/pip" install -q --no-deps --require-hashes -r "$v/.plugin-req"
  fi
  "$v/bin/python" -c 'import torch; assert torch.version.cuda and torch.cuda.is_available()' \
    || die "torch in venv-${v##*/venv-} has no CUDA. Re-run; if it persists, see docs/en/technical.md (Troubleshooting)."
  "$v/bin/vllm" --help >/dev/null 2>&1 || die "vllm in venv-${v##*/venv-} does not start; see the output above"
  rm -f -- "$v/.pkgs"; printf '%s\n' "$sig" >"$v/.pkgs"
}
[ "$WITH_LLM" = 1 ] && llm_venv llm "$VLLM_LLM_VERSION"
# shellcheck disable=SC2086  # the requirement line with its hash, split on purpose
[ "$WITH_KOLIBRI" = 1 ] && llm_venv kolibri "$VLLM_KOLIBRI_VERSION" $KOLIBRI_PLUGIN

# ---------------------------------------------------------------- Bilder malen (optional, plan bildgenerierung)
# The engine is stable-diffusion.cpp's sd-server, built here once per pinned commit (bildmodell.SDCPP_COMMIT) for the
# GB10 (CUDA, sm_121), no Docker; the model files are pinned by revision and SHA-256 (bildmodell.py). Without the
# option nothing of this is fetched or built, and the service stays off.
SDCPP_COMMIT=$(sed -n 's/^SDCPP_COMMIT = "\([0-9a-f]\{40\}\)"$/\1/p' "$INSTALL_FROM/app/bildmodell.py")
if [ "$WITH_BILD" = 1 ]; then
  [ -n "$SDCPP_COMMIT" ] || die "app/bildmodell.py names no stable-diffusion.cpp commit"
  if [ -L "$PREFIX/sdcpp" ] || [ "$(cat "$PREFIX/sdcpp/.built" 2>/dev/null)" != "$SDCPP_COMMIT" ] || [ ! -x "$PREFIX/sdcpp/bin/sd-server" ]; then
    say "Building the picture engine (stable-diffusion.cpp ${SDCPP_COMMIT:0:12}, CUDA; takes a while once)"
    command -v cmake >/dev/null || apt_wait install -y -q cmake || die "cmake could not be installed"
    NVCC=$(command -v nvcc || echo /usr/local/cuda/bin/nvcc)
    [ -x "$NVCC" ] || die "nvcc not found (CUDA toolkit); needed once to build the picture engine"
    rm -rf -- "$PREFIX/sdcpp.new"
    git clone --quiet --no-checkout https://github.com/leejet/stable-diffusion.cpp "$PREFIX/sdcpp.new" \
      || die "could not fetch stable-diffusion.cpp"
    git -C "$PREFIX/sdcpp.new" checkout --quiet "$SDCPP_COMMIT" || die "stable-diffusion.cpp has no commit $SDCPP_COMMIT"
    git -C "$PREFIX/sdcpp.new" submodule update --quiet --init ggml || die "could not fetch ggml for stable-diffusion.cpp"
    nice -n 10 cmake -S "$PREFIX/sdcpp.new" -B "$PREFIX/sdcpp.new/build" -DCMAKE_BUILD_TYPE=Release \
      -DSD_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=121 -DCMAKE_CUDA_COMPILER="$NVCC" \
      -DSD_WEBP=OFF -DSD_WEBM=OFF -DSD_SERVER_BUILD_FRONTEND=OFF >/dev/null || die "cmake for the picture engine failed"
    nice -n 10 cmake --build "$PREFIX/sdcpp.new/build" --target sd-server -j "$(nproc)" >/dev/null \
      || die "building the picture engine failed"
    built=$(find "$PREFIX/sdcpp.new/build" -type f -name sd-server -perm -u+x | head -1)
    [ -n "$built" ] || die "the build left no sd-server"
    install -d -m 755 "$PREFIX/sdcpp.new/bin" && install -m 755 "$built" "$PREFIX/sdcpp.new/bin/sd-server"
    printf '%s\n' "$SDCPP_COMMIT" >"$PREFIX/sdcpp.new/.built"
    rm -rf -- "$PREFIX/sdcpp" && mv -- "$PREFIX/sdcpp.new" "$PREFIX/sdcpp"
  fi
  if [ "$DOWNLOAD" = 1 ]; then
    say "Picture model $(cfg .image.variant) (only what is missing; checked with SHA-256)"
    as_svc mkdir -p -- "$VAR/models/bild"
    # the new app/ is not in place yet: the script comes from the source, read by root (like Parakeet below)
    sudo -u "$SVC_USER" HF_HOME="$VAR/hf" "$PREFIX/venv-panel/bin/python" - download "$(cfg .image.variant)" "$VAR/models/bild" \
      <"$INSTALL_FROM/app/bildmodell.py" || warn "picture model incomplete; run the install again later (Bilder malen says what is missing)"
  fi
fi

# ---------------------------------------------------------------- models (ASR / transformers TTS)
# An update downloads only when the chosen models changed since the last complete download
# ($PREFIX/.models, root's file); the services fetch a model that went missing themselves.
MODELS_SIG="models-r1 $WITH_ASR $WITH_TTS $ASR_BACKEND $BACKEND $(cfgq -c '{a: .asr.model, b: .asr.aligner_model, c: .asr.timestamps, d: .asr.recognizer, e: .tts.model, f: .tts.voicedesign_enabled, g: .tts.voicedesign_model}')"
if [ "$DOWNLOAD" = 1 ] && [ "$FROM_UPDATE" = 1 ] && [ -f "$PREFIX/.models" ] && [ ! -L "$PREFIX/.models" ] \
   && [ "$(cat "$PREFIX/.models")" = "$MODELS_SIG" ]; then
  say "Downloading skipped: the models are the same as before"
  DOWNLOAD=0
fi
MODELS_OK=1
if [ "$PANEL_ONLY" = 1 ]; then   # Notbetrieb mit Parakeet: the model is there before the switch is ever on (offline later)
  say "Downloading the Parakeet recognizer for the emergency mode (~640 MB)"
  { cat "$INSTALL_FROM/app/parakeet.py"; echo 'download()'; } \
    | sudo -u "$SVC_USER" HF_HOME="$VAR/hf" "$PREFIX/venv-panel/bin/python" - \
    || warn "Parakeet download failed; run sudo ./install.sh --mode panel again for the emergency mode"
fi
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
      || { warn "Parakeet download failed; the ASR service retries when it starts"; MODELS_OK=0; }
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
  if [ "$MODELS_OK" = 1 ]; then rm -f -- "$PREFIX/.models"; printf '%s\n' "$MODELS_SIG" >"$PREFIX/.models"; fi
fi

# ---------------------------------------------------------------- self-test (before anything goes live)
# The new code against a fake LLM, TTS and Home Assistant in a throw-away folder. In an update a
# failure stops here, while the running version is untouched.
if [ "${SPEECH_SPARK_NO_SELFTEST:-0}" = 1 ]; then
  say "Self-test skipped (putting the previous version back)"
else
# The whole self-test takes minutes of CPU. When update.sh installs exactly the version GitHub's
# test run passed (SPEECH_SPARK_TESTED=1), a short smoke test here is enough: it loads every module
# with the packages of this Spark and starts the panel once. Otherwise (first install, --newest, a
# chosen version, a clone from elsewhere) the whole self-test runs. Both run with the lowest CPU and
# disk priority, so an answer that is being spoken right now keeps its speed.
SELFTEST_LOG="$PREFIX/selftest.log"
if [ "$FROM_UPDATE" = 1 ] && [ "${SPEECH_SPARK_TESTED:-0}" = 1 ] && [ -f "$INSTALL_FROM/app/tests/test_rauchtest.py" ]; then
  say "Self-test of the panel: smoke test (this version passed GitHub's tests)"
  SELFTEST_ARGS=(-m unittest tests.test_rauchtest)
else
  say "Self-test of the panel (fake LLM and TTS, nothing real is touched)"
  SELFTEST_ARGS=(-m unittest discover -s tests -t .)
fi
# selftest.py: a failed test gets one second try; red twice stays red, green the second time is a WARNUNG line
# (same rule as GitHub's "Tests", Dominik 2026-10-11)
if [ -f "$INSTALL_FROM/app/selftest.py" ]; then
  SELFTEST_ARGS=(selftest.py "${SELFTEST_ARGS[@]:2}")
fi
work=$(mktemp -d); cp -r "$INSTALL_FROM/app" "$work/app"
if (cd "$work/app" && nice -n 19 ionice -c 2 -n 7 timeout 900 "$PREFIX/venv-panel/bin/python" -W ignore "${SELFTEST_ARGS[@]}" >"$SELFTEST_LOG" 2>&1); then
  echo "   $(grep -E '^Ran ' "$SELFTEST_LOG" | head -1) - all passed"
  grep -E '^WARNUNG erst im zweiten Versuch' "$SELFTEST_LOG" | sed 's/^/   /' || true
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
# "Was ist neu" in the panel shows the changelog of exactly this version
if [ -f "$INSTALL_FROM/CHANGELOG.md" ] && [ ! -L "$INSTALL_FROM/CHANGELOG.md" ]; then
  cp -- "$INSTALL_FROM/CHANGELOG.md" "$PREFIX/app.new/CHANGELOG.md"
fi
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
  for u in asr asr-engine tts tts-engine bild tts-design turn llm llmtor sehen; do
    for a in start stop restart; do
      [ $first = 1 ] || printf ', '
      printf '/usr/bin/systemctl %s speech-spark-%s' "$a" "$u"; first=0
    done
  done
  printf ', /usr/bin/systemctl start --no-block speech-spark-update, /usr/bin/systemctl stop speech-spark-update'
  printf ', /usr/bin/systemctl start --no-block speech-spark-wechsel\n'   # stage E4: takes the panel's checked wish
} >/etc/sudoers.d/speech-spark
chmod 440 /etc/sudoers.d/speech-spark
visudo -cf /etc/sudoers.d/speech-spark >/dev/null || die "sudoers file invalid"

# Spark teilen: the door's own certificate (EC P-256, common.TOR_CERT, apart from the panel's), which the panel
# computer pins at the pairing; speech-spark teilen zertifikat is the one place that makes it
if [ "$TEILEN" = 1 ]; then
  SPEECH_SPARK_PREFIX="$PREFIX" SPEECH_SPARK_ETC="$ETC" SPEECH_SPARK_VAR="$VAR" \
    bash "$PREFIX/app/speech-spark.sh" teilen zertifikat || die "could not create the door's certificate"
fi

# ---------------------------------------------------------------- Spark teilen: pairing of the panel computer
# with the model computer named by --modelle (its code: sudo speech-spark teilen code there); nothing of the panel
# starts before, so it never talks to the models without the pinned certificate
if [ -n "$MODELLE_PICK" ] && { [ "$(cfg '.models.host // ""')" != "$MODELLE_PICK" ] || [ -z "$(cfg '.models.cert // ""')" ]; }; then
  say "Pairing with the model computer $MODELLE_PICK (show the code there: sudo speech-spark teilen code)"
  { [ -t 0 ] || [ -n "${SPEECH_SPARK_CODE:-}" ]; } || die "the pairing needs the code: run in a terminal, or give SPEECH_SPARK_CODE"
  SPEECH_SPARK_PREFIX="$PREFIX" SPEECH_SPARK_ETC="$ETC" SPEECH_SPARK_VAR="$VAR" \
    bash "$PREFIX/app/speech-spark.sh" teilen koppeln "$MODELLE_PICK" || die "the pairing did not work; run the install again with a new code"
fi
# a panel computer reaches the language model only through the model computer's LLM-Tor: a chat address on this
# computer (127.0.0.1, such as qwen38's from a move) becomes the door's, on every install and update (V01.0.637)
if [ "$(cfg '(.models.host // "127.0.0.1") | . == "127.0.0.1" or . == "localhost" or . == "::1"')" = false ]; then
  jqi 'if ((.chat.llm_url // "") | test("^https?://(127[.]0[.]0[.]1|localhost|[[]::1[]])([:/]|$)")) then
         .chat.llm_url = "https://\(.models.host | if test(":") then "[\(.)]" else . end):\(.llm.port // 31006)/v1"
         | .chat.llm_key = "" | .chat.llm_model = "" | del(.chat.llm_key_from) else . end'
  # the speakers' address of the panel (Funktionen → Eigene Lautsprecher) moved with the panel: the model computer's
  # name in it becomes this computer's first IPv4 address, scheme and port stay (V01.0.638)
  here=$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -m1 -E '^[0-9]+([.][0-9]+){3}$' || true)
  [ -n "$here" ] && jqi --arg ip "$here" '.models.host as $h
         | if ((.chat.esp32_url // "") | test("^https?://" + ($h | gsub("[.]"; "[.]")) + "(:[0-9]+)?/?$"))
           then .chat.esp32_url |= sub("^(?<s>https?://)[^:/]+"; "\(.s)\($ip)") else . end'
fi

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

# The vLLM engines get no MemoryMax= on purpose: on the GB10 the GPU memory is the same unified memory, so a
# cap could count the model and kill the engine; vLLM's own gpu_memory_utilization and earlyoom bound them.
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
# the own language model and, on demand, the image understanding model (engine.sh reads the catalog, modelle.py);
# speech-spark-sehen is never enabled: the LLM-Tor starts it for a picture question and stops it when idle
engine_unit llm llm
engine_unit sehen sehen
sed -i 's/^Restart=on-failure$/Restart=no/' /etc/systemd/system/speech-spark-sehen.service

# The LLM-Tor (llm_tor.py) on llm.port: API key, field guard, System One, canary; the engines stay on 127.0.0.1.
cat >/etc/systemd/system/speech-spark-llmtor.service <<EOF
[Unit]
Description=Speech on DGX Spark: LLM-Tor (the own language model's door)
After=network-online.target speech-spark-llm.service
Wants=network-online.target

[Service]
LogNamespace=speech-spark
User=$SVC_USER
Group=$SVC_USER
WorkingDirectory=$PREFIX/app
$common_env
ExecStart=$PREFIX/venv-panel/bin/python $PREFIX/app/llm_tor.py
Restart=on-failure
RestartSec=10
MemoryMax=1G
Nice=-5
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF

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
# a small Python loop: a runaway restarts it instead of taking memory from the engines
MemoryMax=1G
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF

# The Vermittler for calls from outside (coturn): never enabled here, the panel starts and stops it with the switch
# "Anrufe von unterwegs" and writes its settings (state/turn.conf, 0600: the relay only reaches public addresses).
cat >/etc/systemd/system/speech-spark-turn.service <<EOF
[Unit]
Description=Speech on DGX Spark: relay for calls (TURN)
After=network-online.target
ConditionPathExists=$VAR/state/turn.conf
ConditionPathExists=/usr/bin/turnserver

[Service]
LogNamespace=speech-spark
User=$SVC_USER
Group=$SVC_USER
ExecStart=/usr/bin/turnserver -c $VAR/state/turn.conf
Restart=on-failure
RestartSec=10
MemoryMax=512M
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=$VAR/state
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
# AF_NETLINK: coturn reads the own addresses (getifaddrs) and stops at once without it
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_NETLINK
CapabilityBoundingSet=
LockPersonality=yes
EOF

# Bilder malen (bild_server.py): only on 127.0.0.1, the panel is its only caller. It starts the picture engine
# (sd-server) as its own child only while painting and stops it after image.idle_min minutes. No MemoryMax= for
# the same reason as the engines above (unified memory); bild_server checks the free memory before it loads and
# is the first one the kernel may stop when memory runs out.
cat >/etc/systemd/system/speech-spark-bild.service <<EOF
[Unit]
Description=Speech on DGX Spark: Bilder malen (FLUX.2 klein)
After=network-online.target $QWEN38_AFTER

[Service]
LogNamespace=speech-spark
User=$SVC_USER
Group=$SVC_USER
WorkingDirectory=$PREFIX/app
$common_env
Environment=SPEECH_SPARK_BILD_DIR=$VAR/models/bild
Environment=SPEECH_SPARK_SD_SERVER=$PREFIX/sdcpp/bin/sd-server
ExecStart=$PREFIX/venv-panel/bin/python $PREFIX/app/bild_server.py
Restart=on-failure
RestartSec=30
TimeoutStopSec=30
KillMode=control-group
OOMScoreAdjust=1000
Nice=10
PrivateTmp=yes

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

# Stage E4: switches one model (speech-spark modelle wechseln, or the panel's Funktionen → Modelle wechseln). It takes
# only the wish file modelle.py wrote and checks every rule again as root; nothing else can be passed in.
cat >/etc/systemd/system/speech-spark-wechsel.service <<EOF
[Unit]
Description=Speech on DGX Spark: switch one model
After=network-online.target

[Service]
LogNamespace=speech-spark
Type=oneshot
Environment=SPEECH_SPARK_PREFIX=$PREFIX SPEECH_SPARK_ETC=$ETC SPEECH_SPARK_VAR=$VAR
ExecStart=/bin/bash $PREFIX/app/speech-spark.sh modelle wunsch-intern
TimeoutStartSec=2h
EOF

# Spark teilen (plan raspberry-split B6b), only on the model computer: the door (tlstor.py, TLS 1.3 on api.tls_listen,
# only api.tls_from), the Wärter (tarswart.py on 127.0.0.1:31007, only with the key from the pairing) and the door's
# firewall at boot (the rules speech-spark teilen firewall wrote into root's /etc after the pairing)
if [ "$TEILEN" = 1 ]; then
cat >/etc/systemd/system/speech-spark-tlstor.service <<EOF
[Unit]
Description=Speech on DGX Spark: TLS-Tor (the door for the panel on another computer)
After=network-online.target speech-spark-teilen-fw.service
Wants=network-online.target

[Service]
LogNamespace=speech-spark
User=$SVC_USER
Group=$SVC_USER
WorkingDirectory=$PREFIX/app
$common_env
Environment=SPEECH_SPARK_TLS=$ETC/tls
ExecStart=$PREFIX/venv-panel/bin/python $PREFIX/app/tlstor.py
Restart=on-failure
RestartSec=10
MemoryMax=512M
NoNewPrivileges=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF
cat >/etc/systemd/system/speech-spark-waerter.service <<EOF
[Unit]
Description=Speech on DGX Spark: Wärter (fixed commands from the panel on another computer)
After=network-online.target
ConditionPathExists=$VAR/state/waerter.key

[Service]
LogNamespace=speech-spark
User=$SVC_USER
Group=$SVC_USER
WorkingDirectory=$PREFIX/app
$common_env
Environment=SPEECH_SPARK_PREFIX=$PREFIX
ExecStart=$PREFIX/venv-panel/bin/python $PREFIX/app/tarswart.py
Restart=on-failure
RestartSec=10
MemoryMax=512M
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF
cat >/etc/systemd/system/speech-spark-teilen-fw.service <<EOF
[Unit]
Description=Speech on DGX Spark: firewall of the door (only the panel computer)
Before=speech-spark-tlstor.service
ConditionPathExists=$(dirname "$ETC")/speech-spark-teilen.nft

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/sbin/nft -f $(dirname "$ETC")/speech-spark-teilen.nft

[Install]
WantedBy=multi-user.target
EOF
else
  systemctl disable --now speech-spark-tlstor.service speech-spark-waerter.service speech-spark-teilen-fw.service 2>/dev/null || true
  rm -f /etc/systemd/system/speech-spark-tlstor.service /etc/systemd/system/speech-spark-waerter.service \
    /etc/systemd/system/speech-spark-teilen-fw.service
fi
# Notbetrieb mit Parakeet (plan raspberry-split B5c), only on the panel computer: the ASR front end with Parakeet on
# 127.0.0.1:31009 (common.NOTASR_PORT); it loads the model at the first recording, only while the model computer is
# gone and chat.notbetrieb_asr is on (panel/notbetrieb.py), and gives the memory back after 10 minutes without one
if [ "$PANEL_ONLY" = 1 ]; then
cat >/etc/systemd/system/speech-spark-notasr.service <<EOF
[Unit]
Description=Speech on DGX Spark: Parakeet for the emergency mode (the model computer is gone)
After=network-online.target

[Service]
LogNamespace=speech-spark
User=$SVC_USER
Group=$SVC_USER
WorkingDirectory=$PREFIX/app
$common_env
Environment=HF_HOME=$VAR/hf HF_HUB_OFFLINE=1 SPEECH_SPARK_NOTASR=1
ExecStart=$PREFIX/venv-panel/bin/python $PREFIX/app/asr_proxy.py
Restart=on-failure
RestartSec=10
MemoryMax=2G
NoNewPrivileges=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
EOF
else
  systemctl disable --now speech-spark-notasr.service 2>/dev/null || true
  rm -f /etc/systemd/system/speech-spark-notasr.service
fi
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
  # bump units-r… when the unit files change in a way a running engine must pick up; a changed engine.sh
  # (its start options) restarts the engines by itself
  set -- "$1" "$2 units-r2 engine.sh=$(sha256sum "$PREFIX/app/engine.sh" | cut -c1-16)"
  systemctl enable "speech-spark-$1.service" >/dev/null 2>&1
  if [ "$FROM_UPDATE" = 0 ] || [ "$(as_svc cat -- "$sigfile" 2>/dev/null)" != "$2" ] \
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
  restart_engine asr-engine "$VLLM_VERSION $(cfgq -c '.asr | {model, engine_mem, engine_max_seqs, engine_port}')"
else
  systemctl disable --now speech-spark-asr-engine.service 2>/dev/null || true
fi
# The ASR and TTS front ends: an update restarts one only when something it runs from changed (its
# files from app/restart-map, its unit, the settings, its Python packages). A service the map does not
# know, or a missing file, always restarts. tests/test_rauchtest.py checks the map against the imports.
svc_print() {  # $1 = service: everything it runs from, as one stream (only hashed, never shown)
  local files f
  files=$(sed -n "s/^$1: *//p" "$PREFIX/app/restart-map" 2>/dev/null | head -1)
  [ -n "$files" ] || { echo "unknown $(date +%s%N)"; return; }
  echo "restart-r1"
  { cat "/etc/systemd/system/speech-spark-$1.service"; cfg_json; } 2>/dev/null
  for f in $files; do
    case "$f" in *..*|/*|*[!A-Za-z0-9_./-]*) echo "bad $(date +%s%N)"; continue ;; esac
    printf '== %s\n' "$f"; cat -- "$PREFIX/app/$f" 2>/dev/null || echo "missing $(date +%s%N)"
  done
  cat -- "$PREFIX"/venv-*/.pkgs "$PREFIX/venv-panel/.locked" 2>/dev/null || true
}
restart_front() {  # $1 = service (asr, tts, bild, llmtor, tlstor, waerter or notasr)
  local fp mark="$PREFIX/.restart-$1"
  fp=$(svc_print "$1" | sha256sum | cut -c1-64)
  systemctl enable "speech-spark-$1.service" >/dev/null 2>&1
  if [ "$FROM_UPDATE" = 0 ] || [ ! -f "$mark" ] || [ -L "$mark" ] || [ "$(cat "$mark")" != "$fp" ] \
     || ! systemctl is-active -q "speech-spark-$1.service"; then
    systemctl restart "speech-spark-$1.service"
    echo "   $1 restarted"
  else
    echo "   $1 unchanged, keeps running"
  fi
  rm -f -- "$mark"; printf '%s\n' "$fp" >"$mark"
}
if [ "$WITH_ASR" = 1 ]; then
  restart_front asr
else
  systemctl disable --now speech-spark-asr.service 2>/dev/null || true
fi

if [ "$WITH_TTS" = 1 ] && [ "$BACKEND" = vllm-omni ]; then
  restart_engine tts-engine "$VLLM_OMNI_VERSION $(cfgq -c '.tts | {model, engine_mem_talker, engine_mem_code2wav, engine_max_seqs, engine_max_model_len, engine_port}')"
  if [ "$(cfg .tts.voicedesign_enabled)" = true ]; then
    # like the engines above: only when its settings changed (a restart loads the VoiceDesign model again)
    restart_engine tts-design "$VLLM_OMNI_VERSION $(cfgq -c '.tts')"
  else
    systemctl disable --now speech-spark-tts-design.service 2>/dev/null || true
  fi
else
  systemctl disable --now speech-spark-tts-engine.service speech-spark-tts-design.service 2>/dev/null || true
fi
if [ "$WITH_TTS" = 1 ]; then
  restart_front tts
else
  systemctl disable --now speech-spark-tts.service 2>/dev/null || true
fi

if [ "$WITH_BILD" = 1 ]; then
  restart_front bild
else
  systemctl disable --now speech-spark-bild.service 2>/dev/null || true
fi

# The own language model runs only once `speech-spark modelle llm uebernehmen` switched llm.enabled on; until then
# qwen38 stays the language model and these units stay off.
if [ "$LLM_ON" = 1 ]; then
  restart_engine llm "$VLLM_LLM_VERSION $(cfgq -c '.llm | {modell, engine_port}') $(sha256sum "$PREFIX/app/modelle.json" | cut -c1-16)"
  restart_front llmtor
else
  systemctl disable --now speech-spark-llmtor.service speech-spark-llm.service 2>/dev/null || true
  systemctl stop speech-spark-sehen.service 2>/dev/null || true
fi

[ "$PANEL_ONLY" = 1 ] && restart_front notasr
if [ "$TEILEN" = 1 ]; then
  systemctl enable speech-spark-teilen-fw.service >/dev/null 2>&1
  systemctl start speech-spark-teilen-fw.service 2>/dev/null || warn "the door's firewall did not load (sudo speech-spark teilen firewall)"
  restart_front tlstor
  restart_front waerter
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
APIS="ASR API:   http://$IP:$ASR_PORT/v1/audio/transcriptions   (backend: $ASR_BACKEND)
 TTS API:   http://$IP:$TTS_PORT/v1/audio/speech   (backend: $BACKEND)"
[ "$PANEL_ONLY" = 1 ] && APIS="Models:    on $(cfg '.models.host') (Spark teilen; check: sudo speech-spark teilen rundlauf)"
if [ "$MODE" = full ]; then
cat <<EOF

------------------------------------------------------------------
 Panel:     http://$IP:$PANEL_PORT   (opens with the assistant; settings need the password: $PASSWORD)
 Voice chat: https://$IP:$HTTPS_PORT  (panel page "Assistent"; accept the self-signed certificate once)
 $APIS
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
# Spark teilen: the model computer waits for its panel computer (a new code later: sudo speech-spark teilen code)
if [ "$TEILEN" = 1 ] && [ "$FROM_UPDATE" = 0 ] && [ "$(cfg '.api.tls_from // [] | length')" = 0 ]; then
  if [ "$ASK" = 1 ]; then
    echo
    echo " Now on the panel computer: sudo ./install.sh --mode panel --modelle $IP  (it asks for this code)"
    bash "$PREFIX/app/speech-spark.sh" teilen code || warn "not paired yet: sudo speech-spark teilen code"
  else
    echo " Spark teilen: show the pairing code with  sudo speech-spark teilen code"
  fi
fi
