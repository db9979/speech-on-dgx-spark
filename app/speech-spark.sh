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
#   speech-spark logs [what] [-n N]  last log lines: asr, tts, asr-engine, tts-engine, tts-design, bild,
#                                  panel, watch, update, messen or all (default)
#   speech-spark panel enable|disable  add the web panel later, or remove it (its data stays)
#   speech-spark notzugang [--yes]  locked out: new panel password, its second step and
#                                  "Benutzer als Admin" off (roles stay), noted and told to the admins
#   speech-spark pause [llm|asr|tts|bild|alles][,…] [min]  Wartungspause while a model is updated (default llm 30)
#   speech-spark pause status      is a Wartungspause running, how long still
#   speech-spark weiter            end the Wartungspause
#   speech-spark modelle liste     the model catalog (app/modelle.json)
#   speech-spark modelle messen [llm] [sehen] [fp8] [gemma] [--yes]  measure catalog models; qwen38 pauses meanwhile
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
    # $ETC belongs to the service user: a fresh file made in /etc (root only), renamed over whatever is there (never followed)
    local tmp; tmp=$(mktemp "$(dirname "$ETC")/.speech-spark-connection.XXXXXX")
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
  for u in asr asr-engine tts tts-engine tts-design bild panel watch; do
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
  if [ "$(cfg '.image.enabled // false')" = true ]; then
    h=$(health "$(cfg .image.port)")
    printf '  %-4s port %s: %s\n' "BILD" "$(cfg .image.port)" "$( [ -n "$h" ] && jq -r '.status' <<<"$h" 2>/dev/null || echo "no answer")"
  fi
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
      tmp=$(mktemp "$(dirname "$ETC")/.speech-spark-config.XXXXXX")   # in root's /etc: nobody else can swap it
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
    asr|tts|asr-engine|tts-engine|tts-design|bild|panel|watch|update) units=(-u "speech-spark-$what") ;;
    messen) units=(-u speech-spark-messen -u speech-spark-messen-engine) ;;
    *) die "logs: asr, tts, asr-engine, tts-engine, tts-design, bild, panel, watch, update, messen or all" ;;
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

# Locked out (V01.0.439): only here, as root on the Spark; the panel itself cannot do this.
# The work runs as the panel's service user, so every file keeps its owner (app/panel/notzugang.py).
cmd_notzugang() {
  need_root notzugang "$@"
  [ "$(mode)" = full ] || die "no web panel installed"
  if [ "${1:-}" != --yes ]; then
    [ -t 0 ] || die "notzugang asks first; run it in a terminal (or add --yes)"
    echo "Das setzt ein neues Panel-Passwort, schaltet den zweiten Schritt des Notzugangs aus (die Datei bleibt"
    echo "als .bak) und „Benutzer als Admin“ aus (die Rollen bleiben). Alle Admin-Anmeldungen enden."
    local a; read -r -p "Weiter? [j/N] " a
    case "$a" in j|J|ja|Ja|y|Y|yes) ;; *) echo "Abgebrochen, nichts geändert."; exit 1 ;; esac
  fi
  as_panel_user notzugang.py
}

panel_user() {
  local svc
  svc=$(systemctl show -p User --value speech-spark-panel.service 2>/dev/null || true)
  [ -n "$svc" ] || svc=$(stat -c %U "$VAR/state")
  [ -n "$svc" ] && [ "$svc" != root ] || die "cannot tell the panel's service user"
  echo "$svc"
}

# A panel module run as the panel's service user, so every file keeps its owner: as_panel_user <file.py> [args]
# (a path relative to app/panel, ../modelle.py for the model catalog)
as_panel_user() {
  local svc
  svc=$(panel_user)
  cd "$PREFIX/app/panel"
  runuser -u "$svc" -- env -i PATH=/usr/bin:/bin LANG=C.UTF-8 PYTHONUNBUFFERED=1 \
    SPEECH_SPARK_CONFIG="$CONFIG" SPEECH_SPARK_STATE="$VAR/state" SPEECH_SPARK_USERS="$VAR/users" \
    SPEECH_SPARK_VOICES="$VAR/voices" SPEECH_SPARK_PREFIX="$PREFIX" HF_HOME="$VAR/hf" \
    "$PREFIX/venv-panel/bin/python" "$PREFIX/app/panel/$1" "${@:2}"
}

# Wartungspause (app/panel/wartung.py): while qwen38, ASR or TTS is updated the Spark pauses on purpose.
cmd_pause() {
  need_root pause "$@"
  [ "$(mode)" = full ] || die "no web panel installed"
  as_panel_user wartung.py "$@"
}

# Modell-Katalog (app/modelle.py, plan plaene/eigene-modelle.md). "messen" (E0) runs in its own unit, so closing
# the terminal never leaves qwen38 stopped: the unit's trap always starts the qwen38 lanes again.
MESS_UNIT=speech-spark-messen
MESS_ENGINE=speech-spark-messen-engine
MESS_PORT=31016
mem_gib() { awk '/^MemAvailable:/ {printf "%.1f", $2 / 1048576}' /proc/meminfo; }

# waits until the free memory stops growing (an engine that just stopped gives it back slowly), at most 3 minutes
mem_settle() {
  local prev now calm=0
  prev=$(mem_gib)
  for _ in $(seq 1 36); do
    sleep 5; now=$(mem_gib)
    if awk -v a="$now" -v b="$prev" 'BEGIN { exit !(a - b < 0.5) }'; then calm=$((calm + 1)); else calm=0; fi
    [ "$calm" -ge 3 ] && break
    prev=$now
  done
}

# weights qwen38 already has: streamed out of its owner's cache by root, written by the service user, checked after
# (modelle.py pruefen); a copy that fails the check is dropped and downloaded instead
hf_from_qwen38() {  # $1 = id, $2 = repo, $3 = revision
  local svc dir src="" h blobs=() f t
  svc=$(panel_user)
  dir="models--${2//\//--}"
  runuser -u "$svc" -- test -d "$VAR/hf/hub/$dir/snapshots/$3" && return 0
  for h in /root $(getent passwd | awk -F: '$3 >= 1000 && $3 < 60000 {print $6}'); do
    t="$h/.cache/huggingface/hub/$dir"
    if [ -d "$t/snapshots/$3" ] && [ ! -L "$t" ] && [ ! -L "$t/snapshots/$3" ]; then src=$t; break; fi
  done
  [ -n "$src" ] || return 0
  echo "modelle: kopie $1 aus dem cache von qwen38"
  while IFS= read -r -d '' f; do
    t=$(readlink -f -- "$f") || continue
    [ "$(dirname -- "$t")" = "$src/blobs" ] && blobs+=("blobs/$(basename -- "$t")")
  done < <(find "$src/snapshots/$3" -type l -print0)
  [ "${#blobs[@]}" -gt 0 ] || return 0
  runuser -u "$svc" -- mkdir -p -- "$VAR/hf/hub/$dir"
  tar -C "$src" -cf - "snapshots/$3" "${blobs[@]}" | runuser -u "$svc" -- tar -C "$VAR/hf/hub/$dir" --no-same-owner -xf - \
    || echo "modelle: kopie $1 fehler"
  if as_panel_user ../modelle.py pruefen "$1"; then return 0; fi
  echo "modelle: kopie $1 verworfen, lade neu"
  runuser -u "$svc" -- rm -rf -- "$VAR/hf/hub/$dir"   # a bad blob would stay in the cache otherwise
}

# one catalog model in its own engine unit, measured, stopped again; returns 3 when it did not work
mess_engine() {  # $1 = id, $2 = commit, $3 = --ohne-mtp or empty
  local svc rc=0 args=() extra=()
  svc=$(panel_user)
  [ -n "${3:-}" ] && extra=("$3")
  mapfile -t args < <(as_panel_user ../modelle.py vllm-args "$1" --port "$MESS_PORT" --revision "$2" "${extra[@]}")
  [ "${#args[@]}" -gt 4 ] || { echo "modelle: messung $1 abgelehnt"; return 2; }
  echo "modelle: messung $1 start${3:+ ohne mtp}"
  systemd-run --quiet --collect --unit="$MESS_ENGINE" -p LogNamespace=speech-spark -p User="$svc" -p Group="$svc" \
    -p WorkingDirectory="$VAR" -p OOMScoreAdjust=500 -p KillMode=control-group -p TimeoutStopSec=30 \
    --setenv=HF_HOME="$VAR/hf" --setenv=HOME="$VAR" --setenv=HF_HUB_OFFLINE=1 --setenv=VLLM_NO_USAGE_STATS=1 \
    --setenv=DO_NOT_TRACK=1 --setenv=PATH="$PREFIX/venv-engine/bin:/usr/local/cuda/bin:/usr/bin:/bin" \
    "$PREFIX/venv-engine/bin/vllm" serve "${args[@]}"
  as_panel_user ../modelle.py messen-lauf "$1" --port "$MESS_PORT" --einheit "$MESS_ENGINE" "${extra[@]}" || rc=$?
  systemctl stop "$MESS_ENGINE" 2>/dev/null || true
  mem_settle
  return "$rc"
}

mess_restore() {
  local u
  systemctl stop "$MESS_ENGINE" 2>/dev/null || true
  for u in "${MESS_QWEN[@]}"; do systemctl start --no-block "$u" || echo "modelle: qwen38 start fehler"; done
  [ "${#MESS_QWEN[@]}" -gt 0 ] && echo "modelle: qwen38 wieder an (${#MESS_QWEN[@]} dienste)"
  [ "$MESS_PAUSE" = 1 ] && { as_panel_user wartung.py weiter || true; }
  as_panel_user ../modelle.py ergebnis || true
  echo "modelle: messung ende"
}

# inside the unit $MESS_UNIT, as root: $@ = catalog ids
cmd_messen_intern() {
  local mid repo rev commit rc minutes ids=() commits=()
  MESS_QWEN=(); MESS_PAUSE=0
  for mid in "$@"; do
    repo=$(as_panel_user ../modelle.py feld "$mid" repo) && rev=$(as_panel_user ../modelle.py feld "$mid" revision) \
      || { echo "modelle: messung $mid abgelehnt"; continue; }
    [ -n "$rev" ] && hf_from_qwen38 "$mid" "$repo" "$rev"
    echo "modelle: lade $mid (falls noch nicht da)"
    if commit=$(as_panel_user ../modelle.py vorbereiten "$mid" | tail -n1) && [[ "$commit" =~ ^[0-9a-f]{40}$ ]]; then
      ids+=("$mid"); commits+=("$commit")
    else
      echo "modelle: messung $mid nicht geladen"
    fi
  done
  [ "${#ids[@]}" -gt 0 ] || { echo "modelle: messung ende nichts geladen"; return 1; }
  if ss -Hltn "sport = :$MESS_PORT" | grep -q .; then echo "modelle: messung abgelehnt port belegt"; return 1; fi
  minutes=$(( ${#ids[@]} * 25 + 10 )); [ "$minutes" -gt 240 ] && minutes=240
  if [ "$(mode)" = full ] && as_panel_user wartung.py status | grep -q '^Keine Wartungspause'; then
    as_panel_user wartung.py llm "$minutes" && MESS_PAUSE=1 || echo "modelle: messung ohne wartungspause"
  fi
  mapfile -t MESS_QWEN < <(systemctl list-units 'qwen38-*' --type=service --state=active,activating --plain --no-legend \
    | awk '{print $1}' | grep -v '^qwen38-dashboard' || true)
  trap mess_restore EXIT
  trap 'exit 1' INT TERM
  if [ "${#MESS_QWEN[@]}" -gt 0 ]; then
    echo "modelle: qwen38 aus (${#MESS_QWEN[@]} dienste), frei vorher $(mem_gib) GiB"
    systemctl stop "${MESS_QWEN[@]}" || true
  fi
  mem_settle
  echo "modelle: frei zum messen $(mem_gib) GiB"
  for i in "${!ids[@]}"; do
    rc=0; mess_engine "${ids[$i]}" "${commits[$i]}" "" || rc=$?
    # the MTP head may be missing from a quantised repo: once more without it, so the numbers still come
    if [ "$rc" = 3 ] && as_panel_user ../modelle.py vllm-args "${ids[$i]}" --revision "${commits[$i]}" | grep -q '^--speculative-config$'; then
      mess_engine "${ids[$i]}" "${commits[$i]}" --ohne-mtp || true
    fi
  done
}

cmd_modelle() {
  need_root modelle "$@"
  case "${1:-liste}" in
    liste) as_panel_user ../modelle.py liste ;;
    messen)
      shift
      local yes=0 was=() ids self follow
      for a in "$@"; do [ "$a" = --yes ] && yes=1 || was+=("$a"); done
      [ -x "$PREFIX/venv-engine/bin/vllm" ] || die "vLLM is not installed ($PREFIX/venv-engine); run the install with a vLLM engine first"
      systemctl is-active -q "$MESS_UNIT" && die "a measurement is running already: sudo speech-spark logs messen"
      systemctl is-active -q speech-spark-update && die "an update is running; measure afterwards"
      ids=$(as_panel_user ../modelle.py messliste "${was[@]}") || die "speech-spark modelle messen [llm] [sehen] [fp8] [gemma] [--yes]"
      echo "Messen: $ids"
      echo "Das lädt fehlende Modelle, stoppt qwen38 für die Messung (pro Modell etwa 10 bis 25 Minuten) und startet es danach wieder."
      if [ "$yes" != 1 ]; then
        [ -t 0 ] || die "messen asks first; run it in a terminal (or add --yes)"
        local a; read -r -p "Weiter? [j/N] " a
        case "$a" in j|J|ja|Ja|y|Y|yes) ;; *) echo "Abgebrochen, nichts geändert."; exit 1 ;; esac
      fi
      self=$(readlink -f -- "$0")
      # shellcheck disable=SC2086  # ids are catalog ids (checked words)
      systemd-run --quiet --collect --unit="$MESS_UNIT" -p LogNamespace=speech-spark -p TimeoutStopSec=180 \
        --setenv=SPEECH_SPARK_PREFIX="$PREFIX" --setenv=SPEECH_SPARK_ETC="$ETC" --setenv=SPEECH_SPARK_VAR="$VAR" \
        "$self" modelle messen-intern $ids
      echo "Die Messung läuft (auch wenn du dieses Fenster schließt). Ergebnis: Zustand → Logs oder sudo speech-spark logs messen"
      journalctl --namespace=speech-spark -u "$MESS_UNIT" -f -n 0 --no-pager -o cat &
      follow=$!
      while systemctl is-active -q "$MESS_UNIT"; do sleep 5; done
      sleep 1; kill "$follow" 2>/dev/null || true
      ;;
    messen-intern) shift; [ "${INVOCATION_ID:-}" ] || die "only inside its own unit"; cmd_messen_intern "$@" ;;
    *) die "speech-spark modelle liste|messen [llm] [sehen] [fp8] [gemma] [--yes]" ;;
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
  notzugang) shift; cmd_notzugang "$@" ;;
  pause) shift; cmd_pause "$@" ;;
  weiter) shift; cmd_pause weiter ;;
  modelle) shift; cmd_modelle "$@" ;;
  ""|-h|--help|help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) die "unknown command: $1 (see: speech-spark help)" ;;
esac
