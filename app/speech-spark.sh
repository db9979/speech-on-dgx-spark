#!/usr/bin/env bash
# Speech on DGX Spark: the command line, for an install without the web panel (and for the shell).
# Installed as /usr/local/bin/speech-spark; run with sudo.
#
#   speech-spark status            services, models, memory, last update
#   speech-spark info [--save]     addresses, API key and examples for other services
#                                  (--save also writes /etc/speech-spark/connection.txt)
#   speech-spark key [new]         show the API key, or make a new one (the old one stops working)
#   speech-spark models            choose the models again (same questions as the first install)
#   speech-spark update [--check]  update to the newest version (like the button in the panel)
#   speech-spark logs [what] [-n N]  last log lines: asr, tts, asr-engine, tts-engine, tts-design,
#                                  panel, watch, update or all (default)
#   speech-spark panel enable|disable  add the web panel later, or remove it (its data stays)
set -euo pipefail

PREFIX=${SPEECH_SPARK_PREFIX:-/opt/speech-spark}
ETC=${SPEECH_SPARK_ETC:-/etc/speech-spark}
VAR=${SPEECH_SPARK_VAR:-/var/lib/speech-spark}
CONFIG="$ETC/config.json"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need_root() { [ "$(id -u)" = 0 ] || die "run with sudo: sudo speech-spark $*"; }
cfg() { jq -r "$1" "$CONFIG"; }
mode() { local m; m=$(cat "$ETC/mode" 2>/dev/null || true); case "$m" in api) echo api ;; *) echo full ;; esac; }
version() { head -1 "$PREFIX/app/VERSION" 2>/dev/null || echo "?"; }
health() { curl -fs --max-time 3 "http://127.0.0.1:$1/health" 2>/dev/null || true; }

# the address other machines use: the first LAN address, or 127.0.0.1 when the APIs only listen there
api_host() {
  if [ "$(cfg '.asr.host')" = 127.0.0.1 ] && [ "$(cfg '.tts.host')" = 127.0.0.1 ]; then
    echo 127.0.0.1
  else
    hostname -I 2>/dev/null | awk '{print $1}'
  fi
}

asr_model() {
  if [ "$(cfg '.asr.enabled')" != true ]; then echo "not installed"
  elif [ "$(cfg '.asr.recognizer // "qwen"')" = parakeet ]; then echo "Parakeet (primeline, CPU)"
  else cfg '.asr.model'; fi
}
tts_model() {
  if [ "$(cfg '.tts.enabled')" != true ]; then echo "not installed"; return; fi
  printf '%s' "$(cfg '.tts.model')"
  [ "$(cfg '.tts.voicedesign_enabled')" = true ] && printf ' + VoiceDesign'
  echo
}

cmd_info() {
  local ip key asr tts auth save=0 out
  [ "${1:-}" = --save ] && save=1
  ip=$(api_host); key=$(cfg '.api.key // ""')
  asr="http://$ip:$(cfg .asr.port)"; tts="http://$ip:$(cfg .tts.port)"
  auth=""; [ -n "$key" ] && auth=" -H \"Authorization: Bearer $key\""
  out=$(
    echo "Speech on DGX Spark $(version)"
    if [ "$(mode)" = api ]; then echo "Installed: only the models with their APIs (no web panel)"
    else echo "Installed: complete, with the web panel on http://$(hostname -I 2>/dev/null | awk '{print $1}'):$(cfg .panel.port)"; fi
    echo
    if [ "$(cfg .asr.enabled)" = true ]; then
      echo "Speech recognition (ASR): $(asr_model)"
      echo "  Endpoint:         $asr/v1/audio/transcriptions"
      echo "  OpenAI base URL:  $asr/v1"
    fi
    if [ "$(cfg .tts.enabled)" = true ]; then
      echo "Speech output (TTS): $(tts_model), default voice $(cfg .tts.default_voice)"
      echo "  Endpoint:         $tts/v1/audio/speech"
      echo "  OpenAI base URL:  $tts/v1"
      echo "  Voices:           $tts/v1/audio/voices"
    fi
    echo "API key:            ${key:-none}   (header: Authorization: Bearer <key>)"
    if [ "$ip" = 127.0.0.1 ]; then echo "Reachable:          only on this machine (127.0.0.1)"
    else echo "Reachable:          from the network"; fi
    echo
    echo "Examples:"
    if [ "$(cfg .tts.enabled)" = true ]; then
      echo "  curl -s $tts/v1/audio/speech$auth -H 'Content-Type: application/json' \\"
      echo "    -d '{\"input\": \"Hallo vom Spark.\", \"language\": \"German\", \"response_format\": \"wav\"}' -o hallo.wav"
      if [ "$(cfg .tts.backend)" = vllm-omni ]; then
        echo "  # streamed while it is generated (server-sent events, PCM 16 bit mono 24 kHz in base64):"
        echo "  curl -sN $tts/v1/audio/speech$auth -H 'Content-Type: application/json' \\"
        echo "    -d '{\"input\": \"Hallo vom Spark.\", \"language\": \"German\", \"stream\": true, \"response_format\": \"pcm\"}'"
      fi
    fi
    if [ "$(cfg .asr.enabled)" = true ]; then
      echo "  curl -s $asr/v1/audio/transcriptions$auth -F file=@hallo.wav -F language=de"
    fi
    echo
    echo "Open WebUI (Admin panel -> Settings -> Audio): engine \"OpenAI\" for STT and TTS, the OpenAI"
    echo "base URLs and the API key from above, any model name, TTS voice e.g. $(cfg .tts.default_voice)."
  )
  if [ "$save" = 1 ]; then
    need_root info --save
    # $ETC belongs to the service user: a fresh file, renamed over whatever is there (never followed)
    local tmp; tmp=$(mktemp "$ETC/.connection.XXXXXX")
    printf '%s\n' "$out" >"$tmp"; chmod 600 "$tmp"; chown root:root "$tmp"
    mv -fT -- "$tmp" "$ETC/connection.txt"
  fi
  printf '%s\n' "$out"
}

cmd_status() {
  local u st h free prog
  echo "Speech on DGX Spark $(version), $( [ "$(mode)" = api ] && echo "only the models with their APIs" || echo "complete, with the web panel")"
  echo "ASR: $(asr_model)"
  echo "TTS: $(tts_model)"
  free=$(awk '/^MemAvailable:/ {printf "%.1f", $2 / 1048576}' /proc/meminfo)
  echo "Free memory: $free GiB (DGX OS starts killing processes at about 8 GiB)"
  echo
  for u in asr asr-engine tts tts-engine tts-design panel watch; do
    st=$(systemctl is-active "speech-spark-$u.service" 2>/dev/null || true)
    [ "$(systemctl is-enabled "speech-spark-$u.service" 2>/dev/null || true)" = enabled ] || [ "$st" = active ] || continue
    printf '  %-26s %s\n' "speech-spark-$u" "$st"
  done
  echo
  for u in asr tts; do
    [ "$(cfg ".$u.enabled")" = true ] || continue
    h=$(health "$(cfg ".$u.port")")
    if [ -z "$h" ]; then printf '  %-4s port %s: no answer\n' "${u^^}" "$(cfg ".$u.port")"
    else printf '  %-4s port %s: %s\n' "${u^^}" "$(cfg ".$u.port")" \
      "$(jq -r '.status + (if .error then ": " + (.error | tostring) else "" end)' <<<"$h" 2>/dev/null || echo "?")"; fi
  done
  prog="$VAR/state/update-progress.json"
  if [ -s "$prog" ]; then
    echo
    jq -r '"Last update: " + (.version // "?") + ", " + (.text // "?") + " (" + ((.updated // 0) | todate) + ")"' "$prog" 2>/dev/null || true
  fi
}

cmd_key() {
  need_root key "$@"
  case "${1:-show}" in
    show) echo "$(cfg '.api.key // ""')" ;;
    new)
      local k tmp
      k="sk-$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
      [ -f "$CONFIG" ] && [ ! -L "$CONFIG" ] || die "$CONFIG is not a plain file"
      # the file belongs to the service user (the panel writes it too); keep owner and mode
      tmp=$(mktemp "$ETC/.config.XXXXXX")
      jq --arg k "$k" '.api.key=$k' "$CONFIG" >"$tmp"
      chown --reference="$CONFIG" "$tmp"; chmod --reference="$CONFIG" "$tmp"
      mv -fT -- "$tmp" "$CONFIG"
      echo "New API key (works at once, the old one no longer does):"
      echo "$k"
      cmd_info --save >/dev/null
      ;;
    *) die "speech-spark key [show|new]" ;;
  esac
}

cmd_logs() {
  local what=all n=50 units=()
  while [ $# -gt 0 ]; do
    case "$1" in -n) n=${2:-50}; shift ;; *) what=$1 ;; esac
    shift
  done
  [[ "$n" =~ ^[0-9]{1,5}$ ]] || die "-n needs a number"
  case "$what" in
    all) units=(-u 'speech-spark-*') ;;
    asr|tts|asr-engine|tts-engine|tts-design|panel|watch|update) units=(-u "speech-spark-$what") ;;
    *) die "logs: asr, tts, asr-engine, tts-engine, tts-design, panel, watch, update or all" ;;
  esac
  journalctl --namespace=speech-spark "${units[@]}" --no-pager -n "$n"
}

cmd_update() {
  need_root update "$@"
  if [ "${1:-}" = --check ]; then exec "$PREFIX/src/update.sh" --check; fi
  # through the update unit, like the panel's button: the watchdog then knows an update runs
  echo "Updating (output follows; the update keeps running if you close this) ..."
  journalctl --namespace=speech-spark -u speech-spark-update -f -n 0 --no-pager -o cat &
  local follow=$!
  local rc=0
  systemctl start speech-spark-update.service || rc=$?
  sleep 1; kill "$follow" 2>/dev/null || true
  if [ "$rc" = 0 ]; then echo "Update finished."; else echo "Update failed; see above (or: sudo speech-spark logs update)."; fi
  return "$rc"
}

cmd_models() {
  need_root models
  [ -t 0 ] || die "models asks questions; run it in a terminal"
  exec "$PREFIX/src/install.sh" --choose-models --no-smoke
}

cmd_panel() {
  need_root panel "$@"
  case "${1:-}" in
    enable) exec "$PREFIX/src/install.sh" --mode full --no-smoke ;;
    disable) exec "$PREFIX/src/install.sh" --mode api --no-smoke ;;
    *) die "speech-spark panel enable|disable" ;;
  esac
}

[ -r "$CONFIG" ] || die "cannot read $CONFIG; run with sudo (or install first)"
case "${1:-}" in
  status) shift; cmd_status ;;
  info) shift; cmd_info "$@" ;;
  key) shift; cmd_key "$@" ;;
  models) shift; cmd_models ;;
  update) shift; cmd_update "$@" ;;
  logs) shift; cmd_logs "$@" ;;
  panel) shift; cmd_panel "$@" ;;
  ""|-h|--help|help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) die "unknown command: $1 (see: speech-spark help)" ;;
esac
