#!/usr/bin/env bash
# Speech on DGX Spark: installs Qwen3-ASR + Qwen3-TTS as systemd services with a web
# panel for config and monitoring. Designed to run next to dgx-spark-qwen38.
#
#   sudo ./install.sh                  # install or update
#   sudo ./install.sh --small          # 0.6B models (least unified memory)
#   sudo ./install.sh --no-tts         # only ASR (or --no-asr)
#   sudo ./install.sh --password XYZ   # panel password (otherwise generated)
#   sudo ./install.sh --no-download    # models download on first start instead
#   sudo ./install.sh --no-smoke       # skip the TTS -> ASR round trip at the end
#   sudo ./install.sh --uninstall      # remove services (keeps models); add --purge for everything
set -euo pipefail

PREFIX=/opt/speech-spark
ETC=/etc/speech-spark
VAR=/var/lib/speech-spark
SVC_USER=speech
TORCH_INDEX=https://download.pytorch.org/whl/cu130
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SMALL=0; WITH_ASR=1; WITH_TTS=1; PASSWORD=""; DOWNLOAD=1; SMOKE=1
while [ $# -gt 0 ]; do
  case "$1" in
    --small) SMALL=1 ;;
    --no-asr) WITH_ASR=0 ;;
    --no-tts) WITH_TTS=0 ;;
    --password) PASSWORD="$2"; shift ;;
    --no-download) DOWNLOAD=0 ;;
    --no-smoke) SMOKE=0 ;;
    --uninstall) shift; exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/uninstall.sh" "$@" ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

say()  { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mWARN:\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "run with sudo"
[ "$(uname -m)" = aarch64 ] || warn "this is $(uname -m), not aarch64; the script targets the DGX Spark"
command -v nvidia-smi >/dev/null || die "nvidia-smi not found; is the NVIDIA driver installed?"
nvidia-smi --query-gpu=name --format=csv,noheader | head -1 | grep -qi gb10 \
  || warn "GPU is not a GB10: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"

# ---------------------------------------------------------------- packages
say "System packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3 python3-venv python3-dev git ffmpeg sox libsox-fmt-all libsndfile1 curl jq iproute2
PY=$(command -v python3)

# ---------------------------------------------------------------- user and dirs
say "Service user and directories"
id "$SVC_USER" >/dev/null 2>&1 || useradd --system --home-dir "$VAR" --shell /usr/sbin/nologin "$SVC_USER"
for g in video render systemd-journal; do getent group "$g" >/dev/null && usermod -aG "$g" "$SVC_USER"; done
install -d -o root -g root -m 755 "$PREFIX"
install -d -o "$SVC_USER" -g "$SVC_USER" -m 750 "$ETC" "$VAR" "$VAR/hf" "$VAR/voices"
rm -rf "$PREFIX/app"
cp -r "$SRC/app" "$PREFIX/app"
chmod -R a+rX "$PREFIX/app"

# ---------------------------------------------------------------- config
# Lanes from dgx-spark-qwen38 that claim most of the unified pool (0.76 / 0.85).
big_lane=""
if systemctl cat qwen38-flash.service >/dev/null 2>&1; then big_lane="qwen38-flash (85 %)"; fi
if systemctl cat qwen38-sglang.service 2>/dev/null | grep -q -- '--mem-fraction-static 0.7'; then big_lane="qwen38-sglang 1M mode (76 %)"; fi

if [ ! -f "$ETC/config.json" ]; then
  say "Writing $ETC/config.json"
  cp "$PREFIX/app/config.default.json" "$ETC/config.json"
  if [ "$SMALL" = 1 ] || [ -n "$big_lane" ]; then
    [ -n "$big_lane" ] && [ "$SMALL" = 0 ] && warn "found $big_lane: choosing the 0.6B models so speech fits next to it"
    tmp=$(mktemp)
    jq '.asr.model="Qwen/Qwen3-ASR-0.6B" | .tts.model="Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"' "$ETC/config.json" >"$tmp"
    mv "$tmp" "$ETC/config.json"
  fi
  tmp=$(mktemp)
  jq --argjson a "$WITH_ASR" --argjson t "$WITH_TTS" '.asr.enabled=($a==1) | .tts.enabled=($t==1)' "$ETC/config.json" >"$tmp"
  mv "$tmp" "$ETC/config.json"
else
  say "Keeping existing $ETC/config.json (adding settings introduced by this version)"
  tmp=$(mktemp)
  jq -s '.[0] * .[1]' "$PREFIX/app/config.default.json" "$ETC/config.json" >"$tmp" && mv "$tmp" "$ETC/config.json"
  if [ "$SMALL" = 1 ]; then
    tmp=$(mktemp)
    jq '.asr.model="Qwen/Qwen3-ASR-0.6B" | .tts.model="Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice"' "$ETC/config.json" >"$tmp"
    mv "$tmp" "$ETC/config.json"
  fi
fi
chown "$SVC_USER:$SVC_USER" "$ETC/config.json"; chmod 640 "$ETC/config.json"

cfg() { jq -r "$1" "$ETC/config.json"; }
ASR_PORT=$(cfg .asr.port); TTS_PORT=$(cfg .tts.port); PANEL_PORT=$(cfg .panel.port)

# ---------------------------------------------------------------- ports
say "Checking ports $ASR_PORT, $TTS_PORT, $PANEL_PORT (dgx-spark-qwen38 uses 30000-30099)"
for p in "$ASR_PORT" "$TTS_PORT" "$PANEL_PORT"; do
  owner=$(ss -ltnpH "sport = :$p" 2>/dev/null | head -1)
  [ -n "$owner" ] || continue
  pid=$(grep -oE 'pid=[0-9]+' <<<"$owner" | head -1 | cut -d= -f2)
  # our own services from a previous install are fine; anything else is a conflict
  if [ -z "$pid" ] || [ "$(ps -o user= -p "$pid" | tr -d ' ')" != "$SVC_USER" ]; then
    die "port $p is already in use: $owner. Change it in $ETC/config.json and re-run."
  fi
done

# ---------------------------------------------------------------- venvs
make_venv() {  # $1 = name, rest = pip packages
  local v="$PREFIX/venv-$1"; shift
  [ -x "$v/bin/python" ] || "$PY" -m venv "$v"
  "$v/bin/pip" install -q -U pip wheel setuptools
  if [ "$1" = "--torch" ]; then
    shift
    # PyPI's aarch64 torch has no CUDA; the cu130 build supports Blackwell (GB10).
    "$v/bin/pip" install -q torch torchaudio --index-url "$TORCH_INDEX"
  fi
  PIP_EXTRA_INDEX_URL="$TORCH_INDEX" "$v/bin/pip" install -q -U "$@"
}

check_cuda() {
  "$PREFIX/venv-$1/bin/python" - <<'EOF' || die "torch in venv-$1 has no CUDA. Re-run; if it persists, see README troubleshooting."
import torch
assert torch.version.cuda and torch.cuda.is_available(), "CPU-only torch"
print(f"   torch {torch.__version__}, CUDA {torch.version.cuda}, {torch.cuda.get_device_name(0)}, arch {torch.cuda.get_arch_list()[-3:]}")
EOF
}

if [ "$WITH_ASR" = 1 ]; then
  say "Python env for Qwen3-ASR (several GB of wheels, takes a while)"
  make_venv asr --torch qwen-asr fastapi "uvicorn[standard]" python-multipart
  check_cuda asr
fi
if [ "$WITH_TTS" = 1 ]; then
  say "Python env for Qwen3-TTS"
  make_venv tts --torch qwen-tts fastapi "uvicorn[standard]" python-multipart
  check_cuda tts
fi
say "Python env for the panel"
make_venv panel fastapi "uvicorn[standard]" python-multipart httpx psutil

# ---------------------------------------------------------------- password
if [ ! -f "$ETC/panel.env" ] || [ -n "$PASSWORD" ]; then
  [ -n "$PASSWORD" ] || PASSWORD=$(head -c 18 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 16)
  printf 'PANEL_PASSWORD=%s\n' "$PASSWORD" >"$ETC/panel.env"
fi
chown "$SVC_USER:$SVC_USER" "$ETC/panel.env"; chmod 600 "$ETC/panel.env"
PASSWORD=$(sed -n 's/^PANEL_PASSWORD=//p' "$ETC/panel.env")

# The panel may start/stop/restart exactly these two units, nothing else.
cat >/etc/sudoers.d/speech-spark <<EOF
$SVC_USER ALL=(root) NOPASSWD: /usr/bin/systemctl start speech-spark-asr, /usr/bin/systemctl stop speech-spark-asr, /usr/bin/systemctl restart speech-spark-asr, /usr/bin/systemctl start speech-spark-tts, /usr/bin/systemctl stop speech-spark-tts, /usr/bin/systemctl restart speech-spark-tts
EOF
chmod 440 /etc/sudoers.d/speech-spark
visudo -cf /etc/sudoers.d/speech-spark >/dev/null || die "sudoers file invalid"

# ---------------------------------------------------------------- systemd
say "systemd units"
QWEN38_AFTER="qwen38-sglang.service qwen38-flash.service qwen38-image.service qwen38-video.service qwen38-llamacpp.service"
unit() {  # $1 = asr|tts
  cat >"/etc/systemd/system/speech-spark-$1.service" <<EOF
[Unit]
Description=Speech on DGX Spark: Qwen3-${1^^}
# Start after the qwen38 lanes so their static memory fraction is claimed first.
After=network-online.target $QWEN38_AFTER
Wants=network-online.target

[Service]
User=$SVC_USER
Group=$SVC_USER
WorkingDirectory=$PREFIX/app
Environment=SPEECH_SPARK_CONFIG=$ETC/config.json
Environment=SPEECH_SPARK_VOICES=$VAR/voices
Environment=HF_HOME=$VAR/hf
Environment=PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
Environment=PYTHONUNBUFFERED=1
ExecStart=$PREFIX/venv-$1/bin/python $PREFIX/app/$1_server.py
Restart=on-failure
RestartSec=10
# If unified memory runs out, the kernel / earlyoom should pick speech before an LLM lane or sshd.
OOMScoreAdjust=900
Nice=5

[Install]
WantedBy=multi-user.target
EOF
}
unit asr; unit tts
cat >/etc/systemd/system/speech-spark-panel.service <<EOF
[Unit]
Description=Speech on DGX Spark: web panel
After=network-online.target

[Service]
User=$SVC_USER
Group=$SVC_USER
WorkingDirectory=$PREFIX/app/panel
Environment=SPEECH_SPARK_CONFIG=$ETC/config.json
Environment=SPEECH_SPARK_VOICES=$VAR/voices
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=$ETC/panel.env
ExecStart=$PREFIX/venv-panel/bin/python $PREFIX/app/panel/panel.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload

# ---------------------------------------------------------------- models
if [ "$DOWNLOAD" = 1 ]; then
  say "Downloading models into $VAR/hf"
  dl() {
    sudo -u "$SVC_USER" HF_HOME="$VAR/hf" "$PREFIX/venv-$1/bin/python" -c \
      "import sys; from huggingface_hub import snapshot_download; snapshot_download(sys.argv[1])" "$2"
  }
  if [ "$WITH_ASR" = 1 ]; then
    dl asr "$(cfg .asr.model)"
    [ "$(cfg .asr.timestamps)" = true ] && dl asr "$(cfg .asr.aligner_model)"
  fi
  [ "$WITH_TTS" = 1 ] && dl tts "$(cfg .tts.model)"
fi

# ---------------------------------------------------------------- start
say "Starting services"
systemctl enable --now speech-spark-panel.service
systemctl restart speech-spark-panel.service
for s in asr tts; do
  if [ "$(cfg .$s.enabled)" = true ] && [ -x "$PREFIX/venv-$s/bin/python" ]; then
    systemctl enable speech-spark-$s.service; systemctl restart speech-spark-$s.service
  else
    systemctl disable --now speech-spark-$s.service 2>/dev/null || true
  fi
done

wait_ready() {  # $1 = name, $2 = port
  local st=""
  for _ in $(seq 1 120); do
    st=$(curl -fs "http://127.0.0.1:$2/health" | jq -r .status 2>/dev/null || true)
    case "$st" in ready) echo "   $1 ready"; return 0 ;; error|blocked)
      echo "   $1 $st: $(curl -fs "http://127.0.0.1:$2/health" | jq -r .error)"; return 1 ;; esac
    sleep 5
  done
  echo "   $1 not ready after 10 min (status: ${st:-no answer}); see: journalctl -u speech-spark-$1"; return 1
}
ok_asr=0; ok_tts=0
[ "$(cfg .asr.enabled)" = true ] && [ "$WITH_ASR" = 1 ] && wait_ready asr "$ASR_PORT" && ok_asr=1
[ "$(cfg .tts.enabled)" = true ] && [ "$WITH_TTS" = 1 ] && wait_ready tts "$TTS_PORT" && ok_tts=1

if [ "$SMOKE" = 1 ] && [ "$ok_tts" = 1 ]; then
  say "Smoke test: TTS -> ASR round trip"
  out=$(mktemp --suffix=.wav)
  curl -fs "http://127.0.0.1:$TTS_PORT/v1/audio/speech" -H 'Content-Type: application/json' \
    -d '{"input":"Hello from the DGX Spark. Speech is up and running.","language":"English"}' -o "$out" \
    && echo "   TTS wrote $(stat -c %s "$out") bytes" || warn "TTS request failed"
  if [ "$ok_asr" = 1 ] && [ -s "$out" ]; then
    curl -fs "http://127.0.0.1:$ASR_PORT/v1/audio/transcriptions" -F "file=@$out" | jq -r '"   ASR heard: \(.text)"' \
      || warn "ASR request failed"
  fi
  rm -f "$out"
fi

IP=$(hostname -I | awk '{print $1}')
cat <<EOF

------------------------------------------------------------------
 Panel:     http://$IP:$PANEL_PORT   (user: anything, password: $PASSWORD)
 ASR API:   http://$IP:$ASR_PORT/v1/audio/transcriptions
 TTS API:   http://$IP:$TTS_PORT/v1/audio/speech
 Config:    $ETC/config.json     Logs: journalctl -u 'speech-spark-*'
------------------------------------------------------------------
EOF
