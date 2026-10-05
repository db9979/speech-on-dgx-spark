#!/usr/bin/env bash
# Speech on DGX Spark: uninstall.
#
#   sudo ./uninstall.sh           # remove services, code, venvs, sudoers rule
#                                 # keeps config, downloaded models and cloned voices
#   sudo ./uninstall.sh --purge   # also delete config, models, voices and the 'speech' user
#   sudo ./uninstall.sh --yes     # no confirmation prompt
#
# Touches nothing that belongs to dgx-spark-qwen38.
set -euo pipefail

PURGE=0; YES=0
for a in "$@"; do
  case "$a" in
    --purge) PURGE=1 ;;
    --yes|-y) YES=1 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }

if [ "$YES" = 0 ]; then
  if [ "$PURGE" = 1 ]; then
    echo "This removes the speech services AND /etc/speech-spark, /var/lib/speech-spark (models, voices) and the user 'speech'."
  else
    echo "This removes the speech services, /opt/speech-spark and the sudoers rule. Config, models and voices are kept."
  fi
  read -r -p "Continue? [y/N] " ans
  case "$ans" in y|Y|j|J|yes|ja) ;; *) echo "Aborted."; exit 1 ;; esac
fi

for s in asr tts tts-engine tts-design panel update; do
  systemctl disable --now "speech-spark-$s.service" 2>/dev/null || true
  rm -f "/etc/systemd/system/speech-spark-$s.service"
done
systemctl daemon-reload
systemctl reset-failed 'speech-spark-*' 2>/dev/null || true
rm -f /etc/sudoers.d/speech-spark
rm -rf /opt/speech-spark   # code, Python envs and the update clone

if [ "$PURGE" = 1 ]; then
  rm -rf /etc/speech-spark /var/lib/speech-spark
  userdel speech 2>/dev/null || true
  echo "Removed everything, including downloaded models and cloned voices."
else
  du -sh /var/lib/speech-spark 2>/dev/null | awk '{print "Kept /etc/speech-spark and /var/lib/speech-spark ("$1"). Remove them with: sudo ./uninstall.sh --purge"}'
fi
