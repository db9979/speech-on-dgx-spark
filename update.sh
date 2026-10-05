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

echo
echo "Updating ..."
git reset --hard --quiet "$new"
if ./install.sh --no-smoke --update; then
  echo
  echo "Update finished: $(git log -1 --format='%h %s')"
else
  rc=$?
  echo
  echo "UPDATE FAILED (exit $rc). The services keep running the previous version."
  git reset --hard --quiet "$old"
  exit "$rc"
fi
