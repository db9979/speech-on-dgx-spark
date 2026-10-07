#!/usr/bin/env bash
# Speech on DGX Spark: update to the newest version on GitHub.
#
#   sudo /opt/speech-spark/src/update.sh           # what the panel's update button runs
#   sudo /opt/speech-spark/src/update.sh --check   # only show what would change
#
# Works on the installer's own clone in /opt/speech-spark/src. Your settings in
# /etc/speech-spark stay. If the new version fails to install, the running services are
# left untouched and the clone goes back to the old version.
set -euo pipefail

SRC=${SPEECH_SPARK_SRC:-/opt/speech-spark/src}
BRANCH=main
CHECK=0
[ "${1:-}" = --check ] && CHECK=1
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
[ -d "$SRC/.git" ] || { echo "$SRC is not a git clone; run install.sh from a git checkout first" >&2; exit 1; }

cd "$SRC"
# Compare with what is installed, not with the clone: an aborted update can leave the
# clone ahead of the installed version.
old=$(jq -r '.commit // empty' "$(dirname "$SRC")/VERSION.json" 2>/dev/null || true)
git cat-file -e "${old:-x}^{commit}" 2>/dev/null || old=$(git rev-parse HEAD)
echo "Installed: $(git log -1 --format='%h %cs %s' "$old")"
echo "Fetching $(git remote get-url origin) ($BRANCH) ..."
git fetch --quiet origin "$BRANCH"
new=$(git rev-parse "origin/$BRANCH")

if [ "$old" = "$new" ]; then
  echo "Already up to date."
  exit 0
fi
echo "Available: $(git log -1 --format='%h %cs %s' "$new")"
echo "Changes:"
git log --format='  %h %s' "$old..$new"
[ "$CHECK" = 1 ] && exit 0

# Progress for the panel (step, text, done + ok at the end); the panel locks itself
# while this runs. install.sh adds one step per section it starts.
export SPEECH_SPARK_PROGRESS=${SPEECH_SPARK_PROGRESS:-/var/lib/speech-spark/state/update-progress.json}
mkdir -p "$(dirname "$SPEECH_SPARK_PROGRESS")"
newver=$(git show "$new:app/VERSION" 2>/dev/null | head -1 || true)
jq -nc --argjson now "$(date +%s)" --arg v "$newver" \
  '{step: 1, text: "Neue Version geladen", started: $now, updated: $now, done: false, ok: null, version: $v}' \
  >"$SPEECH_SPARK_PROGRESS"
chmod 644 "$SPEECH_SPARK_PROGRESS"
finish() {  # ok message
  jq -c --argjson ok "$1" --arg t "$2" --argjson now "$(date +%s)" \
    '.done=true | .ok=$ok | .text=$t | .updated=$now' \
    "$SPEECH_SPARK_PROGRESS" >"$SPEECH_SPARK_PROGRESS.tmp" && mv "$SPEECH_SPARK_PROGRESS.tmp" "$SPEECH_SPARK_PROGRESS"
  chmod 644 "$SPEECH_SPARK_PROGRESS"
}
trap 'finish false "Update abgebrochen"' TERM INT

echo
echo "Updating ..."
git reset --hard --quiet "$new"
if ./install.sh --no-smoke --update; then
  echo
  echo "Update finished: $(git log -1 --format='%h %s')"
  finish true "Fertig"
else
  rc=$?
  echo
  echo "UPDATE FAILED (exit $rc). The services keep running the previous version."
  git reset --hard --quiet "$old"
  finish false "Update fehlgeschlagen (Fehler $rc); die bisherige Version läuft weiter"
  exit "$rc"
fi
