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
#   speech-spark logs [what] [-n N]  last log lines: asr, tts, asr-engine, tts-engine, tts-design, bild, musik,
#                                  llm, llmtor, sehen, tlstor, waerter, notasr, schirm, panel, watch, update, messen, umzug or all (default)
#   speech-spark panel enable|disable  add the web panel later, or remove it (its data stays)
#   speech-spark notzugang [--yes]  locked out: new panel password, its second step and
#                                  "Benutzer als Admin" off (roles stay), noted and told to the admins
#   speech-spark pause [llm|asr|tts|bild|musik|alles][,…] [min]  Wartungspause while a model is updated (default llm 30)
#   speech-spark pause status      is a Wartungspause running, how long still
#   speech-spark weiter            end the Wartungspause
#   speech-spark modelle liste     the model catalog (app/modelle.json)
#   speech-spark modelle messen [llm] [sehen] [fp8] [gemma] [kolibri] [vl30] [eigen-…] [--yes]  measure catalog models; the running language model pauses meanwhile
#   speech-spark modelle llm uebernehmen|zurueck [--yes]  move the chat to the own language model, or back to qwen38
#   speech-spark modelle qwen38-aufraeumen  after the move: qwen38's own uninstall (asks first; never automatic)
#   speech-spark teilen [status]   split install (panel on another computer): door, panel computers, fingerprint
#   speech-spark teilen firewall [aus]  the door's ports only from the panel computer (nftables), or off again
#   speech-spark teilen code       on the model computer: show a pairing code (10 min, once) and wait for the panel
#   speech-spark teilen koppeln <dgx>  on the panel computer: pair with the model computer (asks for the code)
#   speech-spark teilen rundlauf   on the panel computer: Wärter, TTS speaks and ASR hears, through the door
#   speech-spark umziehen --code   give the panel to another computer (shows the code, sends the move backup)
#   speech-spark umziehen --von <host>  take the panel from <host> (asks for its code, restores, checks)
#   speech-spark zurueckholen --von <host>  on the model computer: take the panel back, everything on one computer
#   speech-spark teilen modelle-update  on the panel computer: the model computer's own update (update.sh runs it first)
set -euo pipefail
# runuser, nft, systemctl live in /usr/sbin on Debian and Raspberry Pi OS; a caller with PATH=/usr/bin:/bin (teilen.py
# runs "teilen umzug-einspielen" that way) would not find them
export PATH="$PATH:/usr/local/sbin:/usr/sbin:/sbin"

PREFIX=${SPEECH_SPARK_PREFIX:-/opt/speech-spark}
ETC=${SPEECH_SPARK_ETC:-/etc/speech-spark}
VAR=${SPEECH_SPARK_VAR:-/var/lib/speech-spark}
CONFIG="$ETC/config.json"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
need_root() { [ "$(id -u)" = 0 ] || die "run with sudo: sudo speech-spark $*"; }
cfg() { jq -r "$1" "$CONFIG"; }
# change the config with jq (cfg_put <filter> [jq args]); the file belongs to the service user (the panel writes it
# too), so owner and mode stay, and the temporary file lies in root's /etc where nobody else can swap it
cfg_put() {
  local tmp
  [ -f "$CONFIG" ] && [ ! -L "$CONFIG" ] || die "$CONFIG is not a plain file"
  tmp=$(mktemp "$(dirname "$ETC")/.speech-spark-config.XXXXXX")
  jq "${@:2}" "$1" "$CONFIG" >"$tmp" || { rm -f "$tmp"; die "cannot change $CONFIG"; }
  chown --reference="$CONFIG" "$tmp"; chmod --reference="$CONFIG" "$tmp"
  mv -fT -- "$tmp" "$CONFIG"
}
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
  for u in asr asr-engine tts tts-engine tts-design bild musik panel watch; do
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
  if [ "$(cfg '.music.enabled // false')" = true ]; then
    h=$(health "$(cfg .music.port)")
    printf '  %-4s port %s: %s\n' "MUSIK" "$(cfg .music.port)" "$( [ -n "$h" ] && jq -r '.status' <<<"$h" 2>/dev/null || echo "no answer")"
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
      local k
      k="sk-$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
      cfg_put '.api.key=$k' --arg k "$k"
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
    asr|tts|asr-engine|tts-engine|tts-design|bild|musik|llm|llmtor|sehen|panel|watch|update|tlstor|waerter|notasr|schirm) units=(-u "speech-spark-$what") ;;
    messen) units=(-u speech-spark-messen -u speech-spark-messen-wunsch -u speech-spark-messen-engine) ;;
    umzug) units=(-u speech-spark-umzug -u speech-spark-llm -u speech-spark-llmtor) ;;
    wechsel) units=(-u speech-spark-wechsel -u speech-spark-llm -u speech-spark-sehen) ;;
    *) die "logs: asr, tts, asr-engine, tts-engine, tts-design, bild, musik, llm, llmtor, sehen, tlstor, waerter, notasr, schirm, panel, watch, update, messen, umzug, wechsel or all" ;;
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
# the Wartungspause works with the panel here, or on the model computer of a split install (its panel elsewhere
# honours it, plan Raspberry-Pi split B4c)
can_pause() { [ "$(mode)" = full ] || [ -n "$(cfg '.api.tls_listen // ""')" ]; }

cmd_pause() {
  need_root pause "$@"
  can_pause || die "no web panel installed"
  as_panel_user wartung.py "$@"
}

# Modell-Katalog (app/modelle.py, plan plaene/eigene-modelle.md). "messen" (E0) runs in its own unit, so closing
# the terminal never leaves qwen38 stopped: the unit's trap always starts the qwen38 lanes again.
MESS_UNIT=speech-spark-messen
MESS_ENGINE=speech-spark-messen-engine
MESS_WUNSCH_UNIT=speech-spark-messen-wunsch   # Zustand → Modelle „Messen“: a fixed root unit takes the panel's wish
MESS_PORT=31016
UMZUG_UNIT=speech-spark-umzug
WECHSEL_UNIT=speech-spark-wechsel   # stage E4: a fixed root unit; the panel and the command line leave a wish for it
OWN_LLM=(speech-spark-llmtor speech-spark-llm speech-spark-sehen)
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
  local svc dir src="" h blobs=() f t b hub
  svc=$(panel_user)
  dir="models--${2//\//--}"
  runuser -u "$svc" -- test -d "$VAR/hf/hub/$dir/snapshots/$3" && return 0
  for h in /root $(getent passwd | awk -F: '$3 >= 1000 && $3 < 60000 {print $6}'); do
    t="$h/.cache/huggingface/hub/$dir"
    if [ -d "$t/snapshots/$3" ] && [ ! -L "$t" ] && [ ! -L "$t/snapshots/$3" ]; then src=$t; break; fi
  done
  [ -n "$src" ] || return 0
  echo "modelle: kopie $1 aus dem cache von qwen38"
  # the model's blobs/<hash> may link once more into the shared hub/blobs/<2 hex>/ of newer huggingface_hub:
  # copied as plain files (tar -h), but only blobs the snapshot names that end in one of these two folders
  hub=$(readlink -f -- "$src/..")
  while IFS= read -r -d '' f; do
    t=$(readlink -- "$f") || continue
    b=$(basename -- "$t")
    [ "$t" = "../../blobs/$b" ] || continue
    t=$(readlink -f -- "$src/blobs/$b") || continue
    case "$(dirname -- "$t")" in "$src/blobs"|"$hub"/blobs/??) blobs+=("blobs/$b") ;; esac
  done < <(find "$src/snapshots/$3" -type l -print0)
  [ "${#blobs[@]}" -gt 0 ] || return 0
  runuser -u "$svc" -- mkdir -p -- "$VAR/hf/hub/$dir"
  { tar -C "$src" -cf - "snapshots/$3" | runuser -u "$svc" -- tar -C "$VAR/hf/hub/$dir" --no-same-owner -xf - &&
    tar -C "$src" -hcf - "${blobs[@]}" | runuser -u "$svc" -- tar -C "$VAR/hf/hub/$dir" --no-same-owner -xf - ; } \
    || echo "modelle: kopie $1 fehler"
  if as_panel_user ../modelle.py pruefen "$1"; then return 0; fi
  echo "modelle: kopie $1 verworfen, lade neu"
  runuser -u "$svc" -- rm -rf -- "$VAR/hf/hub/$dir"   # a bad blob would stay in the cache otherwise
}

# one catalog model in its own engine unit, measured, stopped again; returns 3 when it did not work
mess_engine() {  # $1 = id, $2 = commit, $3 = --ohne-mtp or empty
  local svc rc=0 args=() extra=() venv kv env=()
  svc=$(panel_user)
  [ -n "${3:-}" ] && extra=("$3")
  # a few kernel compilers at a time (modelle.KOMPILIEREN), else the first start fills the memory
  while read -r kv; do [[ "$kv" =~ ^[A-Z_]+=[0-9]+$ ]] && env+=("--setenv=$kv"); done < <(as_panel_user ../modelle.py kompilieren)
  mapfile -t args < <(as_panel_user ../modelle.py vllm-args "$1" --port "$MESS_PORT" --revision "$2" "${extra[@]}")
  [ "${#args[@]}" -gt 4 ] || { echo "modelle: messung $1 abgelehnt"; return 2; }
  # the entry's own venv (venv-llm, venv-kolibri); before install.sh --llm the engines' venv measures the others
  venv="$PREFIX/venv-$(as_panel_user ../modelle.py venv "$1")"
  if [ ! -x "$venv/bin/vllm" ]; then
    if [ "$venv" = "$PREFIX/venv-llm" ] && [ -x "$PREFIX/venv-engine/bin/vllm" ]; then venv="$PREFIX/venv-engine"
    else echo "modelle: messung $1 abgelehnt venv fehlt"; return 2; fi
  fi
  echo "modelle: messung $1 start${3:+ ohne mtp}"
  systemd-run --quiet --collect --unit="$MESS_ENGINE" -p LogNamespace=speech-spark -p User="$svc" -p Group="$svc" \
    -p WorkingDirectory="$VAR" -p OOMScoreAdjust=500 -p KillMode=control-group -p TimeoutStopSec=30 \
    --setenv=HF_HOME="$VAR/hf" --setenv=HOME="$VAR" --setenv=HF_HUB_OFFLINE=1 --setenv=VLLM_NO_USAGE_STATS=1 \
    --setenv=DO_NOT_TRACK=1 --setenv=PATH="$venv/bin:/usr/local/cuda/bin:/usr/bin:/bin" "${env[@]}" \
    "$venv/bin/vllm" serve "${args[@]}"
  as_panel_user ../modelle.py messen-lauf "$1" --port "$MESS_PORT" --einheit "$MESS_ENGINE" --revision "$2" "${extra[@]}" || rc=$?
  systemctl stop "$MESS_ENGINE" 2>/dev/null || true
  mem_settle
  return "$rc"
}

mess_restore() {
  local u
  systemctl stop "$MESS_ENGINE" 2>/dev/null || true
  for u in "${MESS_QWEN[@]}"; do systemctl start --no-block "$u" || echo "modelle: qwen38 start fehler"; done
  [ "${#MESS_QWEN[@]}" -gt 0 ] && echo "modelle: sprachmodell wieder an (${#MESS_QWEN[@]} dienste)"
  [ "$MESS_PAUSE" = 1 ] && { as_panel_user wartung.py weiter || true; }
  as_panel_user ../modelle.py ergebnis || true
  echo "modelle: messung ende"
}

# inside the unit $MESS_UNIT (or $MESS_WUNSCH_UNIT), as root: $@ = catalog ids
cmd_messen_intern() {
  local mid repo rev commit out rc minutes ids=() commits=()
  MESS_QWEN=(); MESS_PAUSE=0
  for mid in "$@"; do
    repo=$(as_panel_user ../modelle.py feld "$mid" repo) && rev=$(as_panel_user ../modelle.py feld "$mid" revision) \
      || { echo "modelle: messung $mid abgelehnt"; continue; }
    [ -n "$rev" ] && hf_from_qwen38 "$mid" "$repo" "$rev"
    echo "modelle: lade $mid (falls noch nicht da)"
    out=$(as_panel_user ../modelle.py vorbereiten "$mid") || true
    commit=$(tail -n1 <<<"$out")
    if [[ "$commit" =~ ^[0-9a-f]{40}$ ]]; then
      ids+=("$mid"); commits+=("$commit")
    else
      grep '^modelle: ' <<<"$out" || true      # the reason (a fixed word: download, hash, dateiart …)
      echo "modelle: messung $mid nicht geladen"
    fi
  done
  [ "${#ids[@]}" -gt 0 ] || { echo "modelle: messung ende nichts geladen"; return 1; }
  minutes=$(( ${#ids[@]} * 25 + 10 )); [ "$minutes" -gt 240 ] && minutes=240
  if can_pause && as_panel_user wartung.py status | grep -q '^Keine Wartungspause'; then
    as_panel_user wartung.py llm "$minutes" && MESS_PAUSE=1 || echo "modelle: messung ohne wartungspause"
  fi
  mapfile -t MESS_QWEN < <(systemctl list-units 'qwen38-*' speech-spark-llm.service speech-spark-llmtor.service \
    --type=service --state=active,activating --plain --no-legend | awk '{print $1}' | grep -v '^qwen38-dashboard' || true)
  trap mess_restore EXIT
  trap 'exit 1' INT TERM
  if [ "${#MESS_QWEN[@]}" -gt 0 ]; then
    echo "modelle: sprachmodell aus (${#MESS_QWEN[@]} dienste), frei vorher $(mem_gib) GiB"
    systemctl stop "${MESS_QWEN[@]}" || true
  fi
  mem_settle
  # only now: the own language model's engine listens on the same port (31016) until it is stopped above; checked
  # before, every measurement next to the own model ended with "port belegt" (tars 2026-10-16)
  if ss -Hltn "sport = :$MESS_PORT" | grep -q .; then echo "modelle: messung abgelehnt port belegt"; return 1; fi
  echo "modelle: frei zum messen $(mem_gib) GiB"
  for i in "${!ids[@]}"; do
    rc=0; mess_engine "${ids[$i]}" "${commits[$i]}" "" || rc=$?
    # the MTP head may be missing from a quantised repo: once more without it, so the numbers still come
    if [ "$rc" = 3 ] && as_panel_user ../modelle.py vllm-args "${ids[$i]}" --revision "${commits[$i]}" | grep -q '^--speculative-config$'; then
      mess_engine "${ids[$i]}" "${commits[$i]}" --ohne-mtp || true
    fi
  done
}

# inside $MESS_WUNSCH_UNIT, as root (Zustand → Modelle „Messen“): only the ids modelle.py takes from the panel's
# wish, checked again; the same rules as the command line, then the same measurement
cmd_messen_wunsch() {
  local ids=() mid
  read -r -a ids < <(as_panel_user ../modelle.py messen-wunsch-nehmen) || true
  [ "${#ids[@]}" -gt 0 ] || { echo "modelle: messung abgelehnt wunsch"; return 1; }
  for mid in "${ids[@]}"; do
    [[ "$mid" =~ ^[a-z0-9][a-z0-9.-]{1,47}$ ]] || { echo "modelle: messung abgelehnt wunsch"; return 1; }
  done
  { [ -x "$PREFIX/venv-llm/bin/vllm" ] || [ -x "$PREFIX/venv-engine/bin/vllm" ]; } \
    || { echo "modelle: messung abgelehnt venv fehlt"; return 1; }
  if systemctl is-active -q "$MESS_UNIT" "$WECHSEL_UNIT" speech-spark-update; then
    echo "modelle: messung abgelehnt laeuft"; return 1
  fi
  echo "modelle: messung aus dem panel ${#ids[@]} modell"
  cmd_messen_intern "${ids[@]}"
}

# ---------------------------------------------------------------- the move (stage E3), inside $UMZUG_UNIT as root
qwen38_running() {
  systemctl list-units 'qwen38-*' --type=service --state=active,activating --plain --no-legend \
    | awk '{print $1}' | grep -v '^qwen38-dashboard' || true
}

umzug_zurueck() {  # everything as noted before the move; qwen38 starts again
  local u units=()
  systemctl disable --now "${OWN_LLM[@]}" 2>/dev/null || true
  as_panel_user ../modelle.py umzug-schalten zurueck || echo "modelle: zurueck fehler einstellung"
  mapfile -t units < <(as_panel_user ../modelle.py umzug-vorher)
  for u in "${units[@]}"; do
    systemctl enable "$u" 2>/dev/null || true
    systemctl start --no-block "$u" || echo "modelle: qwen38 start fehler"
  done
  as_panel_user ../modelle.py umzug-fertig || true
  echo "modelle: zurueck qwen38 an (${#units[@]} dienste)"
}

umzug_abbruch() {
  [ "$UMZUG_OK" = 1 ] && return 0
  echo "modelle: uebernahme abgebrochen ${UMZUG_GRUND:-fehler}"
  umzug_zurueck
  [ "$UMZUG_PAUSE" = 1 ] && { as_panel_user wartung.py weiter || true; }
}

cmd_umzug_intern() {
  local mid repo rev units=()
  UMZUG_OK=0; UMZUG_PAUSE=0; UMZUG_GRUND=""
  if [ "$1" = zurueck ]; then
    [ -n "$(as_panel_user ../modelle.py umzug-vorher)" ] || { echo "modelle: zurueck abgelehnt keine notiz"; return 1; }
    umzug_zurueck
    tuer_neu
    return 0
  fi
  read -r mid repo rev < <(as_panel_user ../modelle.py umzug-modell) || true
  [[ "${rev:-}" =~ ^[0-9a-f]{40}$ ]] || { echo "modelle: uebernahme abgelehnt katalog (erst sudo speech-spark modelle messen)"; return 1; }
  [ -x "$PREFIX/venv-$(as_panel_user ../modelle.py venv llm)/bin/vllm" ] \
    || { echo "modelle: uebernahme abgelehnt venv fehlt (sudo ./install.sh --llm, für Kolibri --kolibri)"; return 1; }
  hf_from_qwen38 "$mid" "$repo" "$rev"
  echo "modelle: lade $mid (falls noch nicht da)"
  as_panel_user ../modelle.py vorbereiten "$mid" >/dev/null || { echo "modelle: uebernahme abgelehnt nicht geladen"; return 1; }
  mapfile -t units < <(qwen38_running)
  as_panel_user ../modelle.py umzug-merken "${units[@]}" || { echo "modelle: uebernahme abgelehnt schon umgezogen"; return 1; }
  trap umzug_abbruch EXIT
  trap 'exit 1' INT TERM
  if can_pause && as_panel_user wartung.py status | grep -q '^Keine Wartungspause'; then
    as_panel_user wartung.py llm 60 && UMZUG_PAUSE=1 || echo "modelle: uebernahme ohne wartungspause"
  fi
  if [ "${#units[@]}" -gt 0 ]; then
    echo "modelle: qwen38 aus (${#units[@]} dienste, bleiben installiert)"
    systemctl stop "${units[@]}" || true
    systemctl disable "${units[@]}" 2>/dev/null || true
  fi
  mem_settle
  as_panel_user ../modelle.py umzug-schalten an || { UMZUG_GRUND=einstellung; return 1; }
  systemctl enable --now speech-spark-llm.service speech-spark-llmtor.service || { UMZUG_GRUND=start; return 1; }
  echo "modelle: $mid startet, frei $(mem_gib) GiB"
  as_panel_user ../modelle.py rundlauf || { UMZUG_GRUND=rundlauf; return 1; }
  as_panel_user ../modelle.py umzug-schalten um || { UMZUG_GRUND=einstellung; return 1; }
  UMZUG_OK=1
  [ "$UMZUG_PAUSE" = 1 ] && { as_panel_user wartung.py weiter || true; }
  echo "modelle: umgeschaltet $mid"
  tuer_neu
}

run_umzug() {  # $1 = uebernehmen|zurueck: in its own unit, so a closed terminal never leaves the chat without a model
  local self follow
  systemctl is-active -q "$UMZUG_UNIT" && die "a move is running already: sudo speech-spark logs umzug"
  systemctl is-active -q "$MESS_UNIT" "$MESS_WUNSCH_UNIT" && die "a measurement is running; move afterwards"
  systemctl is-active -q speech-spark-update && die "an update is running; move afterwards"
  self=$(readlink -f -- "$0")
  systemd-run --quiet --collect --unit="$UMZUG_UNIT" -p LogNamespace=speech-spark -p TimeoutStopSec=180 \
    --setenv=SPEECH_SPARK_PREFIX="$PREFIX" --setenv=SPEECH_SPARK_ETC="$ETC" --setenv=SPEECH_SPARK_VAR="$VAR" \
    /bin/bash "$self" modelle umzug-intern "$1"
  journalctl --namespace=speech-spark -u "$UMZUG_UNIT" -f -n 0 --no-pager -o cat &
  follow=$!
  while systemctl is-active -q "$UMZUG_UNIT"; do sleep 5; done
  sleep 1; kill "$follow" 2>/dev/null || true
}

# Stage E4 (plan plaene/eigene-modelle.md): switch the model of one kind. Runs only inside speech-spark-wechsel, which
# takes the wish the panel (Funktionen → Modelle wechseln) or `modelle wechseln` left; modelle.py checks every rule
# again here (catalog only, pinned commit, budget). asr, tts and bild go through install.sh with its short key; llm and
# sehen download, check, switch the configuration and restart; the language model passes a round trip or goes back.
install_flag() {
  case "$1" in asr) echo --asr ;; tts) echo --tts ;; bild) echo --bild ;; *) return 1 ;; esac
}

wechsel() {  # $1 = art, $2 = id
  local art=$1 mid=$2 alt out kind repo rev commit pause=0 ok=0
  out=$(as_panel_user ../modelle.py wechsel-pruefen "$art" "$mid") \
    || { grep '^modelle: ' <<<"$out" || true; echo "modelle: wechsel $art abgelehnt"; return 1; }
  read -r kind repo rev <<<"$(tail -n1 <<<"$out")"
  alt=$(as_panel_user ../modelle.py jetzt "$art")
  echo "modelle: wechsel $art startet"
  if [ "$kind" = wahl ]; then
    if "$PREFIX/src/install.sh" "$(install_flag "$art")" "$repo" --yes --no-smoke; then
      ok=1
    elif [ "$alt" != - ]; then
      echo "modelle: wechsel $art fehler, zurueck"
      "$PREFIX/src/install.sh" "$(install_flag "$art")" "$(as_panel_user ../modelle.py feld "$alt" wahl)" --yes --no-smoke \
        || echo "modelle: wechsel $art zurueck fehler"
    fi
  else
    [ -x "$PREFIX/venv-$(as_panel_user ../modelle.py venv "$mid")/bin/vllm" ] \
      || { echo "modelle: wechsel $art abgelehnt venv fehlt (sudo ./install.sh --llm, für Kolibri --kolibri)"; return 1; }
    hf_from_qwen38 "$mid" "$repo" "$rev"
    out=$(as_panel_user ../modelle.py vorbereiten "$mid" --revision "$rev") || true
    commit=$(tail -n1 <<<"$out")
    [ "$commit" = "$rev" ] || { grep '^modelle: ' <<<"$out" || true; echo "modelle: wechsel $art abgelehnt nicht geladen"; return 1; }
    if [ "$art" = llm ] && can_pause && as_panel_user wartung.py status | grep -q '^Keine Wartungspause'; then
      as_panel_user wartung.py llm 30 && pause=1 || echo "modelle: wechsel ohne wartungspause"
    fi
    as_panel_user ../modelle.py wechsel-schalten "$art" "$mid" || { echo "modelle: wechsel $art abgelehnt einstellung"; return 1; }
    if [ "$art" = sehen ]; then
      systemctl stop speech-spark-sehen.service || true    # on demand: the next picture starts the new model
      ok=1
    else
      systemctl stop speech-spark-llm.service || true
      mem_settle
      systemctl start speech-spark-llm.service || true
      if as_panel_user ../modelle.py rundlauf; then
        ok=1
      else
        echo "modelle: wechsel llm fehler, zurueck"
        as_panel_user ../modelle.py wechsel-schalten llm "$alt" || echo "modelle: wechsel llm zurueck fehler"
        systemctl restart speech-spark-llm.service || true
      fi
    fi
    [ "$pause" = 1 ] && { as_panel_user wartung.py weiter || true; }
  fi
  [ "$ok" = 1 ] || { echo "modelle: wechsel $art zurueckgenommen"; return 1; }
  as_panel_user ../modelle.py wechsel-merken "$art" "$alt" "$mid" || true
  echo "modelle: umgeschaltet $art $mid"
}

cmd_wunsch_intern() {
  local art was out
  out=$(as_panel_user ../modelle.py wunsch-nehmen) || true
  read -r art was <<<"$(tail -n1 <<<"$out")"
  if systemctl is-active -q "$MESS_UNIT" "$MESS_WUNSCH_UNIT"; then echo "modelle: wechsel abgelehnt misst"; return 1; fi
  [[ "${was:-}" =~ ^[a-z0-9][a-z0-9.-]{1,47}$ ]] || { echo "modelle: wechsel abgelehnt wunsch"; return 1; }
  if [ "$was" = zurueck ]; then
    out=$(as_panel_user ../modelle.py zurueck-ziel "$art") || true
    was=$(tail -n1 <<<"$out")
    [[ "$was" =~ ^[a-z0-9][a-z0-9.-]{1,47}$ ]] && [[ "$was" != modelle:* ]] \
      || { grep '^modelle: ' <<<"$out" || true; echo "modelle: zurueck $art abgelehnt"; return 1; }
    echo "modelle: zurueck $art auf $was"
  fi
  wechsel "$art" "$was"
}

run_wechsel() {  # $1 = art, $2 = id or zurueck: the wish, then the fixed unit (keeps running when the terminal closes)
  local follow rc=0
  systemctl cat "$WECHSEL_UNIT.service" >/dev/null 2>&1 || die "the unit is missing; run sudo speech-spark update first"
  for u in "$WECHSEL_UNIT" "$UMZUG_UNIT" "$MESS_UNIT" "$MESS_WUNSCH_UNIT" speech-spark-update; do
    systemctl is-active -q "$u" && die "$u is running; switch afterwards"
  done
  as_panel_user ../modelle.py wunsch-schreiben "$1" "$2" || die "speech-spark modelle wechseln llm|sehen|asr|tts|bild <id> (ids: speech-spark modelle liste)"
  echo "Wechsel läuft (auch wenn du dieses Fenster schließt): sudo speech-spark logs wechsel"
  journalctl --namespace=speech-spark -u "$WECHSEL_UNIT" -f -n 0 --no-pager -o cat &
  follow=$!
  systemctl start "$WECHSEL_UNIT.service" || rc=$?
  sleep 1; kill "$follow" 2>/dev/null || true
  return "$rc"
}

cmd_entfernen() {  # $1 = id, $2 = --yes or empty: the cache folder of a catalog model no kind runs any more
  local out dir svc
  out=$(as_panel_user ../modelle.py entfernbar "$1") || true
  dir=$(tail -n1 <<<"$out")
  [[ "$dir" == "$VAR/hf/hub/models--"* ]] || { grep '^modelle: ' <<<"$out" || true; echo "modelle: entfernen $1 abgelehnt"; return 1; }
  echo "Entfernen: $dir ($(du -sh -- "$dir" 2>/dev/null | cut -f1))"
  ask_yes "${2:-}"
  svc=$(panel_user)
  if runuser -u "$svc" -- rm -rf -- "$dir"; then echo "modelle: entfernt $1"; else echo "modelle: entfernen $1 fehler"; return 1; fi
}

ask_yes() {  # $1 = --yes or empty
  [ "${1:-}" = --yes ] && return 0
  [ -t 0 ] || die "this asks first; run it in a terminal (or add --yes)"
  local a; read -r -p "Weiter? [j/N] " a
  case "$a" in j|J|ja|Ja|y|Y|yes) ;; *) echo "Abgebrochen, nichts geändert."; exit 1 ;; esac
}

cmd_qwen38_aufraeumen() {
  local d="" h tor port
  port=$(cfg '.llm.port // 31006'); [[ "$port" =~ ^[0-9]{4,5}$ ]] || port=31006
  tor=$(curl -fs "http://127.0.0.1:$port/health" | jq -r .status 2>/dev/null || true)
  [ "$(cfg '.llm.enabled // false')" = true ] && [ "$tor" = ready ] \
    || die "first move to the own language model (sudo speech-spark modelle llm uebernehmen); it must answer"
  for h in /root $(getent passwd | awk -F: '$3 >= 1000 && $3 < 60000 {print $6}'); do
    [ -f "$h/dgx-spark-qwen38/uninstall.sh" ] && [ ! -L "$h/dgx-spark-qwen38/uninstall.sh" ] && { d="$h/dgx-spark-qwen38"; break; }
  done
  [ -n "$d" ] || die "qwen38's uninstall.sh not found (looked for ~/dgx-spark-qwen38/uninstall.sh); remove it by hand"
  echo "qwen38 liegt in $d. Was seine Deinstallation entfernt:"
  bash "$d/uninstall.sh" --list || true
  echo "Das löscht qwen38 (Dienste, Modelle im Cache von qwen38). Das eigene Sprachmodell bleibt."
  ask_yes ""
  echo "modelle: qwen38 aufraeumen start"
  if bash "$d/uninstall.sh"; then echo "modelle: qwen38 aufraeumen fertig"; else echo "modelle: qwen38 aufraeumen fehler"; return 1; fi
}

cmd_modelle() {
  need_root modelle "$@"
  case "${1:-liste}" in
    liste) as_panel_user ../modelle.py liste ;;
    messen)
      shift
      local yes=0 was=() ids self follow
      for a in "$@"; do [ "$a" = --yes ] && yes=1 || was+=("$a"); done
      [ -x "$PREFIX/venv-llm/bin/vllm" ] || [ -x "$PREFIX/venv-engine/bin/vllm" ] \
        || die "vLLM is not installed ($PREFIX/venv-llm); run sudo ./install.sh --llm first"
      systemctl is-active -q "$MESS_UNIT" "$MESS_WUNSCH_UNIT" && die "a measurement is running already: sudo speech-spark logs messen"
      systemctl is-active -q speech-spark-update && die "an update is running; measure afterwards"
      ids=$(as_panel_user ../modelle.py messliste "${was[@]}") || die "speech-spark modelle messen [llm] [sehen] [fp8] [gemma] [kolibri] [vl30] [eigen-…] [--yes]"
      echo "Messen: $ids"
      echo "Das lädt fehlende Modelle, stoppt das laufende Sprachmodell (eigenes oder qwen38) für die Messung (pro Modell etwa 10 bis 25 Minuten) und startet es danach wieder."
      if [ "$yes" != 1 ]; then
        [ -t 0 ] || die "messen asks first; run it in a terminal (or add --yes)"
        local a; read -r -p "Weiter? [j/N] " a
        case "$a" in j|J|ja|Ja|y|Y|yes) ;; *) echo "Abgebrochen, nichts geändert."; exit 1 ;; esac
      fi
      self=$(readlink -f -- "$0")
      # shellcheck disable=SC2086  # ids are catalog ids (checked words)
      systemd-run --quiet --collect --unit="$MESS_UNIT" -p LogNamespace=speech-spark -p TimeoutStopSec=180 \
        --setenv=SPEECH_SPARK_PREFIX="$PREFIX" --setenv=SPEECH_SPARK_ETC="$ETC" --setenv=SPEECH_SPARK_VAR="$VAR" \
        /bin/bash "$self" modelle messen-intern $ids
      echo "Die Messung läuft (auch wenn du dieses Fenster schließt). Ergebnis: Zustand → Logs oder sudo speech-spark logs messen"
      journalctl --namespace=speech-spark -u "$MESS_UNIT" -f -n 0 --no-pager -o cat &
      follow=$!
      while systemctl is-active -q "$MESS_UNIT"; do sleep 5; done
      sleep 1; kill "$follow" 2>/dev/null || true
      ;;
    messen-intern) shift; [ "${INVOCATION_ID:-}" ] || die "only inside its own unit"; cmd_messen_intern "$@" ;;
    messen-wunsch-intern) [ "${INVOCATION_ID:-}" ] || die "only inside its own unit"; cmd_messen_wunsch ;;
    llm)
      case "${2:-}" in
        uebernehmen)
          [ -x "$PREFIX/venv-llm/bin/vllm" ] || die "vLLM for the own model is not installed; run sudo ./install.sh --llm first"
          systemctl cat speech-spark-llm.service >/dev/null 2>&1 || die "the units are missing; run sudo speech-spark update first"
          echo "Umzug: qwen38 wird gestoppt und deaktiviert (nicht gelöscht), das eigene Sprachmodell startet und wird geprüft."
          echo "Klappt die Prüfung nicht, geht alles von selbst zurück. Etwa 5 bis 20 Minuten ohne Sprachmodell."
          ask_yes "${3:-}"; run_umzug uebernehmen ;;
        zurueck)
          echo "Zurück: das eigene Sprachmodell geht aus, qwen38 startet wieder mit der alten Adresse."
          ask_yes "${3:-}"; run_umzug zurueck ;;
        *) die "speech-spark modelle llm uebernehmen|zurueck [--yes]" ;;
      esac ;;
    umzug-intern) shift; [ "${INVOCATION_ID:-}" ] || die "only inside its own unit"; cmd_umzug_intern "$@" ;;
    qwen38-aufraeumen) cmd_qwen38_aufraeumen ;;
    wechseln) [ $# -ge 3 ] || die "speech-spark modelle wechseln llm|sehen|asr|tts|bild <id>"; run_wechsel "$2" "$3" ;;
    zurueckholen) [ $# -ge 2 ] || die "speech-spark modelle zurueckholen llm|sehen|asr|tts|bild"; run_wechsel "$2" zurueck ;;
    entfernen) [ $# -ge 2 ] || die "speech-spark modelle entfernen <id> [--yes]"; cmd_entfernen "$2" "${3:-}" ;;
    wunsch-intern) [ "${INVOCATION_ID:-}" ] || die "only inside its own unit"; cmd_wunsch_intern ;;
    *) die "speech-spark modelle liste|messen [llm] [sehen] [fp8] [gemma] [kolibri] [vl30] [eigen-…] [--yes]|llm uebernehmen|zurueck|qwen38-aufraeumen|wechseln <art> <id>|zurueckholen <art>|entfernen <id>" ;;
  esac
}

teilen_py() {  # app/teilen.py with the system python (stdlib only; the DGX in --mode api has no panel venv)
  env -i PATH=/usr/bin:/bin LANG=C.UTF-8 SPEECH_SPARK_CONFIG="$CONFIG" SPEECH_SPARK_TLS="${TEILEN_TLS:-$ETC/tls}" \
    SPEECH_SPARK_STATE="$VAR/state" ${SPEECH_SPARK_CODE:+SPEECH_SPARK_CODE="$SPEECH_SPARK_CODE"} \
    python3 "$PREFIX/app/teilen.py" "$@"
}

# the certificate the pairing shows, copied as the service user into root's own folder <dir> (root never reads a path
# in the service user's $ETC): the door's (tor-*), or on a panel computer that gives the panel back the panel's own
tls_kopie() {
  local svc f
  svc=$(panel_user)
  for f in tor-cert.pem tor-key.pem cert.pem key.pem; do
    runuser -u "$svc" -- cat -- "$ETC/tls/$f" >"$1/$f" 2>/dev/null || rm -f "$1/$f"
  done
  [ -s "$1/tor-cert.pem" ] || [ -s "$1/cert.pem" ] || die "no certificate in $ETC/tls"
}

# B6b/B6c: the door's own certificate (EC P-256, common.TOR_CERT), made once by the service user in its own folder;
# the one place that makes it (install.sh --teilen and umziehen --code use this)
tor_zertifikat() {
  local svc san ip
  [ -s "$ETC/tls/tor-cert.pem" ] && return 0
  svc=$(panel_user)
  san="DNS:localhost,DNS:$(hostname),DNS:$(hostname).local,IP:127.0.0.1"
  for ip in $(hostname -I 2>/dev/null); do case "$ip" in *:*) ;; *) san="$san,IP:$ip" ;; esac; done
  runuser -u "$svc" -- sh -c 'umask 077; mkdir -p "$1"' sh "$ETC/tls"
  runuser -u "$svc" -- openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 3650 \
    -subj "/CN=$(hostname) speech-spark tor" -addext "subjectAltName=$san" \
    -keyout "$ETC/tls/tor-key.pem" -out "$ETC/tls/tor-cert.pem" >/dev/null 2>&1 || die "could not create the door's certificate"
  echo "teilen: zertifikat erstellt"
}

# the Wärter key from a pairing result (teilen.py warten|koppeln) into STATE/waerter.key, 0600; written by the owner
# of STATE itself (root never writes into a folder another user can plant links in)
waerter_key_setzen() {
  local own wk
  own=$(stat -c %U "$VAR/state")
  [ -n "$own" ] && [ "$own" != root ] || die "cannot tell the owner of $VAR/state"
  wk=$(jq -r '.waerter_key' "$1")
  [[ "$wk" =~ ^[0-9a-f]{64}$ ]] || die "pairing result without a Wärter key"
  printf '%s\n' "$wk" | runuser -u "$own" -- sh -c \
    'umask 077; t=$(mktemp "$1/.waerter.key.XXXXXX") && cat >"$t" && mv -fT -- "$t" "$1/waerter.key"' sh "$VAR/state"
}

restart_if_there() { local u; for u in "$@"; do systemctl try-restart "$u" 2>/dev/null || true; done; }
# the door opens the LLM-Tor's port only while llm.enabled (tlstor.ports): after the language model's move on a model
# computer of a split install the door and its firewall take the new port list (V01.0.639: the Pi got no answer)
tuer_neu() {
  [ -n "$(cfg '.api.tls_listen // ""')" ] || return 0
  restart_if_there speech-spark-tlstor
  cmd_teilen firewall || true
}
models_here() { case "$(cfg '.models.host // "127.0.0.1"')" in 127.0.0.1|localhost|::1) return 0 ;; *) return 1 ;; esac; }

# the model computer after a pairing: the door opens for exactly that panel computer (its address, the Wärter key)
tuer_oeffnen() {
  waerter_key_setzen "$1"
  cfg_put '.api.tls_from=[$r.von] | .api.key=$r.api_key | .api.tls_listen=(if (.api.tls_listen // "") == "" then $r.hier else .api.tls_listen end)' \
    --argjson r "$(jq -c '{von, hier, api_key}' "$1")"
  cmd_teilen firewall || true
}

# B6a: the model computer shows a pairing code and waits; on a fit the door opens for exactly that panel computer
teilen_code() {
  local tmp
  [ -s "$ETC/tls/tor-cert.pem" ] || die "no door certificate in $ETC/tls (sudo ./install.sh --mode api --teilen)"
  tmp=$(mktemp -d)   # root's own folder, never the service user's $ETC
  tls_kopie "$tmp"
  if ! TEILEN_TLS="$tmp" teilen_py warten "$tmp/ergebnis.json"; then rm -rf "$tmp"; return 1; fi
  tuer_oeffnen "$tmp/ergebnis.json"
  rm -rf "$tmp"
  restart_if_there speech-spark-tlstor speech-spark-waerter   # the services read api.key at every request
  echo "teilen: gekoppelt, die Tür ist offen für den Panel-Rechner"
}

# B6a/B6c: pair with <host> (asks for the code). rolle panel: this computer runs the panel and pins the model
# computer's certificate; rolle zurueck: the model computer takes the panel back and runs everything again. A move
# the other side sends is restored on the way (teilen umzug-einspielen), before anything else changes here.
teilen_koppeln() {
  local host=${1:-} rolle=${2:-panel} tmp
  [[ "$host" =~ ^[A-Za-z0-9.:-]{1,253}$ ]] || die "speech-spark teilen koppeln <name-oder-ip des Modell-Rechners>"
  tmp=$(mktemp -d)   # root's own folder
  if ! teilen_py koppeln "$host" "$tmp/ergebnis.json" "$tmp" -- /bin/bash "$PREFIX/app/speech-spark.sh" teilen umzug-einspielen; then
    rm -rf "$tmp"; return 1
  fi
  if [ "$rolle" = zurueck ]; then
    cfg_put '.models.host="127.0.0.1" | .models.cert="" | .api.tls_from=[] | .api.tls_listen=""'
    rm -rf "$tmp"
    nft delete table inet speech_spark_teilen 2>/dev/null || true
    rm -f "$(dirname "$ETC")/speech-spark-teilen.nft"
    echo "teilen: panel zurück, alles läuft wieder auf diesem Rechner"
    "$PREFIX/src/install.sh" --mode full --yes --no-smoke
    return
  fi
  waerter_key_setzen "$tmp/ergebnis.json"
  cfg_put '.models.host=$h | .models.cert=$r.pem | .api.key=$r.api_key' \
    --arg h "$host" --argjson r "$(jq -c '{pem, api_key}' "$tmp/ergebnis.json")"
  local umzug
  umzug=$(jq -r '.umzug // false' "$tmp/ergebnis.json")
  rm -rf "$tmp"
  restart_if_there speech-spark-panel
  echo "teilen: gekoppelt mit dem Modell-Rechner"
  if [ "$umzug" = true ]; then
    # the model computer switches to the door now (install.sh --teilen, its services restart): wait for it
    echo "teilen: der Modell-Rechner stellt um, Rundlauf wartet höchstens 20 Minuten"
    local i
    for i in $(seq 1 40); do as_panel_user steuer.py rundlauf >/dev/null 2>&1 && break; sleep 30; done
    umzug_handgriffe
  fi
  as_panel_user steuer.py rundlauf || echo "teilen: rundlauf noch nicht grün (Modelle laden noch?): sudo speech-spark teilen rundlauf"
}

# B6c: restore the move the pairing brought (<dir>/umzug.json and umzug.tar.gz, root's folder) as the panel's user
umzug_einspielen() {
  local dir=${1:-}
  [ -s "$dir/umzug.json" ] && [ -s "$dir/umzug.tar.gz" ] || die "no move in $dir"
  { cat "$dir/umzug.json"; echo; cat "$dir/umzug.tar.gz"; } | as_panel_user umziehen.py auspacken
}

# B6c: what stays to do by hand after a move, for the computer that runs the panel now
umzug_handgriffe() {
  local ip
  ip=$(hostname -I 2>/dev/null | awk '{print $1}')
  echo
  echo "Noch von Hand (das Panel läuft jetzt auf $ip):"
  echo "  - Router: Weiterleitung 31443 und TURN (UDP 3478, 49160-49200) auf $ip"
  echo "  - Home Assistant: Wyoming auf $ip:31003"
  echo "  - ESP32-Lautsprecher: Server-Adresse $ip"
}

# B6c: give the panel to another computer (it runs: sudo speech-spark umziehen --von <this>). Only after its signed
# "fertig ok" does this computer change its role: the model computer then runs as --mode api --teilen, a panel
# computer just stops its panel. A failed or broken-off move changes nothing here; nothing is ever deleted.
umzug_geben() {
  local tmp pw
  [ "$(mode)" = full ] || die "there is no panel on this computer to move"
  models_here && tor_zertifikat
  tmp=$(mktemp -d)   # root's own folder
  tls_kopie "$tmp"
  pw=$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)
  printf '%s\n' "$pw" >"$tmp/passwort"
  if ! printf '%s\n' "$pw" | as_panel_user umziehen.py packen >"$tmp/umzug.bin"; then
    rm -rf "$tmp"; die "the move backup could not be made"
  fi
  echo "Auf dem neuen Rechner: sudo speech-spark umziehen --von $(hostname -I 2>/dev/null | awk '{print $1}')"
  if ! TEILEN_TLS="$tmp" teilen_py warten "$tmp/ergebnis.json" "$tmp" \
     || [ "$(jq -r '.umzug_ok // false' "$tmp/ergebnis.json")" != true ]; then
    rm -rf "$tmp"
    echo "teilen: umzug abgebrochen, auf diesem Rechner bleibt alles, wie es war"
    return 1
  fi
  if models_here; then
    tuer_oeffnen "$tmp/ergebnis.json"
    rm -rf "$tmp"
    echo "teilen: umzug fertig, dieser Rechner läuft jetzt nur noch mit den Modellen"
    "$PREFIX/src/install.sh" --mode api --teilen --yes --no-smoke
  else
    rm -rf "$tmp"
    systemctl disable --now speech-spark-panel.service 2>/dev/null || true
    echo "teilen: umzug fertig, das Panel auf diesem Rechner ist aus (seine Daten bleiben)"
  fi
}

cmd_umziehen() {
  need_root umziehen "$@"
  case "${1:-}" in
    --code) umzug_geben ;;
    --von) [ "$(mode)" = full ] || die "install the panel first: sudo ./install.sh --mode panel --modelle <host>"
           teilen_koppeln "${2:-}" panel ;;
    *) die "speech-spark umziehen --code (where the panel is now) | --von <host> (where it goes)" ;;
  esac
}

cmd_zurueckholen() {
  need_root zurueckholen "$@"
  [ "${1:-}" = --von ] || die "speech-spark zurueckholen --von <panel computer> (there: sudo speech-spark umziehen --code)"
  { [ "$(mode)" = api ] && [ -f "$ETC/teilen" ]; } || die "only the model computer of a split install takes the panel back"
  teilen_koppeln "${2:-}" zurueck
}

cmd_teilen() {  # Spark teilen (plan raspberry-split B3): the TLS-Tor's state and its firewall
  need_root teilen "$@"
  local rules n
  rules="$(dirname "$ETC")/speech-spark-teilen.nft"   # root's /etc: the unit speech-spark-teilen-fw loads it at boot
  case "${1:-status}" in
    status)
      n=$(cfg '.api.tls_from // [] | length')
      if [ -n "$(cfg '.api.tls_listen // ""')" ]; then echo "Tür (TLS-Tor):      an, für $n Panel-Rechner"; else echo "Tür (TLS-Tor):      aus (alles auf diesem Rechner)"; fi
      echo "Dienst:             $(systemctl is-active speech-spark-tlstor 2>/dev/null || true)"
      if nft list table inet speech_spark_teilen >/dev/null 2>&1; then echo "Firewall:           an"; else echo "Firewall:           aus"; fi
      echo "Fingerabdruck:      $(teilen_py fingerabdruck)"
      case "$(cfg '.models.host // "127.0.0.1"')" in
        127.0.0.1|localhost|::1) ;;
        *) echo "Modell-Rechner:     $(cfg '.models.host') (Zertifikat gemerkt: $([ -n "$(cfg '.models.cert // ""')" ] && echo ja || echo nein))" ;;
      esac ;;
    firewall)
      if [ "${2:-}" = aus ]; then
        nft delete table inet speech_spark_teilen 2>/dev/null || true
        rm -f "$rules"; echo "teilen: firewall aus"; return 0
      fi
      teilen_py regeln >"$rules.part" || { rm -f "$rules.part"; echo "teilen: firewall abgelehnt"; return 1; }
      if nft -f "$rules.part"; then mv "$rules.part" "$rules"; echo "teilen: firewall gesetzt"
      else rm -f "$rules.part"; echo "teilen: firewall fehler"; return 1; fi ;;
    code) teilen_code ;;
    zertifikat) tor_zertifikat ;;
    umzug-einspielen) umzug_einspielen "${2:-}" ;;
    rundlauf) as_panel_user steuer.py rundlauf ;;
    koppeln) teilen_koppeln "${2:-}" ;;
    modelle-update)   # B5: the model computer updates itself (its own rules) and this one waits for it
      [ "$(mode)" = full ] || die "no web panel installed"
      as_panel_user steuer.py update ;;
    *) die "speech-spark teilen [status]|firewall [aus]|code|koppeln <dgx>|rundlauf|modelle-update" ;;
  esac
}

# Gehäuse (plan Raspberry-Pi split B7, gehaeuse.py): the case of a panel computer. Root writes everything itself from
# two whole numbers (the fan thresholds), never a line from the panel: the block between the markers in config.txt,
# the module i2c-dev and the groups of the service user. A change needs a restart: GEHAEUSE_NEUSTART in /run says so
# (gone after it), and only then the panel's "Neu starten" restarts the Pi.
GEHAEUSE_TXT=${SPEECH_SPARK_CONFIG_TXT:-/boot/firmware/config.txt}
GEHAEUSE_NEUSTART=${SPEECH_SPARK_GEHAEUSE_NEUSTART:-/run/speech-spark-gehaeuse-neustart}
GEHAEUSE_MODULE=${SPEECH_SPARK_MODULES_D:-/etc/modules-load.d}/speech-spark-gehaeuse.conf
GEHAEUSE_BEGIN="# speech-spark gehaeuse begin"
GEHAEUSE_END="# speech-spark gehaeuse end"

gehaeuse_ohne() {  # config.txt without our block (stdin -> stdout), trailing empty lines dropped
  awk -v b="$GEHAEUSE_BEGIN" -v e="$GEHAEUSE_END" '$0 == b { skip = 1; next } $0 == e { skip = 0; next } !skip' \
    | sed -e :a -e '/^\n*$/{$d;N;ba' -e '}'
}

gehaeuse_schreiben() {  # $1 = the new content of config.txt; written next to it and renamed (a copy of the old stays)
  local new="$GEHAEUSE_TXT.speech-spark.part"
  if [ "$1" = "$(cat "$GEHAEUSE_TXT")" ]; then return 1; fi
  cp -p -- "$GEHAEUSE_TXT" "$GEHAEUSE_TXT.speech-spark-alt"
  printf '%s\n' "$1" >"$new" && mv -f -- "$new" "$GEHAEUSE_TXT"
  : >"$GEHAEUSE_NEUSTART"
}

gehaeuse_ein() {  # $1 = fan on at (°C), $2 = fan off below (°C)
  local an=$1 aus=$2 svc g new
  [[ "$an" =~ ^[0-9]{2}$ && "$aus" =~ ^[0-9]{2}$ ]] && [ "$an" -ge 40 ] && [ "$an" -le 80 ] && [ "$aus" -ge 30 ] \
    && [ "$aus" -lt "$an" ] || { echo "gehaeuse: abgelehnt grenzen"; return 1; }
  [ -f "$GEHAEUSE_TXT" ] || { echo "gehaeuse: abgelehnt kein raspberry pi"; return 1; }
  new="$(gehaeuse_ohne <"$GEHAEUSE_TXT")
$GEHAEUSE_BEGIN
[all]
dtparam=i2c_arm=on
dtparam=spi=on
dtoverlay=gpio-fan,gpiopin=6,temp=$((an * 1000)),hyst=$(((an - aus) * 1000))
$GEHAEUSE_END"
  if gehaeuse_schreiben "$new"; then echo "gehaeuse: config.txt geschrieben"; else echo "gehaeuse: config.txt unveraendert"; fi
  mkdir -p -- "$(dirname "$GEHAEUSE_MODULE")"
  printf 'i2c-dev\n' >"$GEHAEUSE_MODULE"
  modprobe i2c-dev 2>/dev/null || true
  svc=$(panel_user)
  for g in i2c spi gpio; do
    getent group "$g" >/dev/null && usermod -aG "$g" "$svc" && echo "gehaeuse: gruppe $g"
  done
  echo "gehaeuse: eingerichtet"
}

gehaeuse_aus() {
  [ -f "$GEHAEUSE_TXT" ] || { echo "gehaeuse: abgelehnt kein raspberry pi"; return 1; }
  if gehaeuse_schreiben "$(gehaeuse_ohne <"$GEHAEUSE_TXT")"; then echo "gehaeuse: config.txt geschrieben"
  else echo "gehaeuse: config.txt unveraendert"; fi
  rm -f -- "$GEHAEUSE_MODULE"
  echo "gehaeuse: entfernt"
}

gehaeuse_neustart() {
  [ -e "$GEHAEUSE_NEUSTART" ] || { echo "gehaeuse: neustart abgelehnt nicht noetig"; return 1; }
  echo "gehaeuse: neustart"
  systemctl reboot
}

cmd_gehaeuse() {
  local out w an aus
  case "${1:-status}" in
    wunsch-intern)   # only inside speech-spark-gehaeuse: the panel's wish, checked again by gehaeuse.py
      [ "${INVOCATION_ID:-}" ] || die "only inside its own unit"
      out=$(as_panel_user gehaeuse.py wunsch-nehmen) || true
      read -r w an aus <<<"$(tail -n1 <<<"$out")"
      case "$w" in
        ein) gehaeuse_ein "$an" "$aus" ;;
        aus) gehaeuse_aus ;;
        neustart) gehaeuse_neustart ;;
        *) echo "gehaeuse: abgelehnt wunsch"; return 1 ;;
      esac ;;
    ein) need_root gehaeuse ein; gehaeuse_ein "${2:-$(cfg '.chat.gehaeuse_luefter_an // 55')}" "${3:-$(cfg '.chat.gehaeuse_luefter_aus // 48')}" ;;
    aus) need_root gehaeuse aus; gehaeuse_aus ;;
    status)
      if grep -qxF "$GEHAEUSE_BEGIN" "$GEHAEUSE_TXT" 2>/dev/null; then echo "Gehäuse: eingerichtet"; else echo "Gehäuse: nicht eingerichtet"; fi
      [ -e "$GEHAEUSE_NEUSTART" ] && echo "Neustart nötig"
      [ -e /dev/i2c-1 ] && echo "I2C: an" || echo "I2C: aus"
      [ -e /dev/spidev0.0 ] && echo "SPI: an" || echo "SPI: aus" ;;
    *) die "speech-spark gehaeuse [status]|ein [AN AUS]|aus" ;;
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
  teilen) shift; cmd_teilen "$@" ;;
  umziehen) shift; cmd_umziehen "$@" ;;
  zurueckholen) shift; cmd_zurueckholen "$@" ;;
  gehaeuse) shift; cmd_gehaeuse "$@" ;;
  ""|-h|--help|help) sed -n '2,31p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) die "unknown command: $1 (see: speech-spark help)" ;;
esac
