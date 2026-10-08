#!/usr/bin/env bash
# Speech on DGX Spark: update to the newest version on GitHub.
#
#   sudo /opt/speech-spark/src/update.sh           # what the panel's update button runs
#   sudo /opt/speech-spark/src/update.sh --check   # only show what would change
#   sudo /opt/speech-spark/src/update.sh --to <commit>   # install that version (e.g. go back one)
#
# The panel's "back to the previous version" button writes the commit into
# /var/lib/speech-spark/state/update-target and starts this script; only commits that are part
# of the official branch are accepted.
#
# Works on the installer's own clone in /opt/speech-spark/src. Your settings in
# /etc/speech-spark stay. If the new version fails before it goes live (downloads, packages,
# self-test), the running services are left untouched and the clone goes back to the old version.
# If it fails after that, the previous version is installed again.
set -euo pipefail

SRC=${SPEECH_SPARK_SRC:-/opt/speech-spark/src}
BRANCH=main
# no way back to before this commit from the panel (V01.0.75: root no longer runs config values)
SECURITY_FLOOR=7373d1a3bb8df864631ec1f722b839b86e445cdb
CHECK=0
TARGET=""
[ "${1:-}" = --check ] && CHECK=1
[ "${1:-}" = --to ] && TARGET=${2:-}
STATE=${SPEECH_SPARK_STATE:-/var/lib/speech-spark/state}
FROM_PANEL=0
if [ -z "$TARGET" ] && [ -s "$STATE/update-target" ] && [ ! -L "$STATE/update-target" ]; then
  TARGET=$(head -c 64 "$STATE/update-target" | tr -dc '0-9a-f')
  FROM_PANEL=1
fi
rm -f "$STATE/update-target"
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
if [ -n "$TARGET" ]; then
  # only versions that are part of the official branch
  if ! git cat-file -e "$TARGET^{commit}" 2>/dev/null || ! git merge-base --is-ancestor "$TARGET" "origin/$BRANCH"; then
    echo "Version $TARGET is not part of $BRANCH; nothing changed." >&2
    exit 1
  fi
  new=$(git rev-parse "$TARGET")
  if [ "$FROM_PANEL" = 1 ]; then
    # The state folder belongs to the service user, so this file is no proof the admin asked for it:
    # accept only the version root itself kept as "previous", and never one from before the
    # security fixes (an old install.sh ran config values as commands, as root).
    prev=$(jq -r '.commit // empty' "$(dirname "$SRC")/VERSION.prev.json" 2>/dev/null || true)
    if [ "$new" != "$prev" ] || ! git merge-base --is-ancestor "$SECURITY_FLOOR" "$new"; then
      echo "Version $TARGET is not the previous version this Spark ran; nothing changed." >&2
      exit 1
    fi
  fi
  echo "Going to the chosen version instead of the newest."
fi

if [ "$old" = "$new" ]; then
  echo "Already up to date."
  exit 0
fi
echo "Available: $(git log -1 --format='%h %cs %s' "$new")"
echo "Changes:"
if git merge-base --is-ancestor "$new" "$old"; then
  echo "  (back to an older version; these changes are undone:)"
  git log --format='  %h %s' "$new..$old"
else
  git log --format='  %h %s' "$old..$new"
fi
[ "$CHECK" = 1 ] && exit 0

# Progress for the panel (step, text, done + ok at the end); the panel locks itself
# while this runs. install.sh adds one step per section it starts.
export SPEECH_SPARK_PROGRESS=${SPEECH_SPARK_PROGRESS:-/var/lib/speech-spark/state/update-progress.json}
mkdir -p "$(dirname "$SPEECH_SPARK_PROGRESS")"
newver=$(git show "$new:app/VERSION" 2>/dev/null | head -1 || true)
# the state folder belongs to the service user: never write through a link planted there
rm -rf -- "$SPEECH_SPARK_PROGRESS" "$SPEECH_SPARK_PROGRESS.tmp"
jq -nc --argjson now "$(date +%s)" --arg v "$newver" \
  '{step: 1, text: "Neue Version geladen", started: $now, updated: $now, done: false, ok: null, version: $v}' \
  >"$SPEECH_SPARK_PROGRESS"
chmod 644 "$SPEECH_SPARK_PROGRESS"
finish() {  # ok message
  rm -f -- "$SPEECH_SPARK_PROGRESS.tmp"
  jq -c --argjson ok "$1" --arg t "$2" --argjson now "$(date +%s)" \
    '.done=true | .ok=$ok | .text=$t | .updated=$now' \
    "$SPEECH_SPARK_PROGRESS" >"$SPEECH_SPARK_PROGRESS.tmp" && mv "$SPEECH_SPARK_PROGRESS.tmp" "$SPEECH_SPARK_PROGRESS"
  chmod 644 "$SPEECH_SPARK_PROGRESS"
}
trap 'finish false "Update abgebrochen"' TERM INT

echo
echo "Updating ..."
# the version running now becomes "the previous version" the panel can go back to
[ -f "$(dirname "$SRC")/VERSION.json" ] && cp "$(dirname "$SRC")/VERSION.json" "$(dirname "$SRC")/VERSION.prev.json.new"
git reset --hard --quiet "$new"
SWITCHED="$(dirname "$SRC")/.switched"
rm -f "$SWITCHED"
if ./install.sh --no-smoke --update; then
  rm -f "$SWITCHED"
  echo
  echo "Update finished: $(git log -1 --format='%h %s')"
  [ -f "$(dirname "$SRC")/VERSION.prev.json.new" ] && mv "$(dirname "$SRC")/VERSION.prev.json.new" "$(dirname "$SRC")/VERSION.prev.json"
  finish true "Fertig"
else
  rc=$?
  echo
  git reset --hard --quiet "$old"
  rm -f "$(dirname "$SRC")/VERSION.prev.json.new"
  if [ -f "$SWITCHED" ]; then
    # the new code was already live: put the previous version back the same way
    rm -f "$SWITCHED"
    echo "UPDATE FAILED (exit $rc) after the new version went live. Installing the previous version again ..."
    # (an older install.sh does not know newer options; the environment variable it just ignores)
    if SPEECH_SPARK_NO_SELFTEST=1 ./install.sh --no-smoke --update; then
      rm -f "$SWITCHED"
      finish false "Update fehlgeschlagen (Fehler $rc); die bisherige Version wurde wieder eingespielt"
    else
      rm -f "$SWITCHED"
      echo "Putting the previous version back failed too; see the output above." >&2
      finish false "Update fehlgeschlagen (Fehler $rc), Zurückspielen auch; bitte Protokoll ansehen"
    fi
  else
    echo "UPDATE FAILED (exit $rc). The services keep running the previous version."
    finish false "Update fehlgeschlagen (Fehler $rc); die bisherige Version läuft weiter"
  fi
  exit "$rc"
fi
