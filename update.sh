#!/usr/bin/env bash
# Speech on DGX Spark: update to the newest version on GitHub.
#
#   sudo /opt/speech-spark/src/update.sh           # what the panel's update button runs
#   sudo /opt/speech-spark/src/update.sh --check   # only show what would change
#   sudo /opt/speech-spark/src/update.sh --to <commit>   # install that version (e.g. go back one)
#   sudo /opt/speech-spark/src/update.sh --newest  # the newest version even before GitHub's tests passed
#   sudo /opt/speech-spark/src/update.sh --lokal   # Entwickeln auf dem Pi: install spark-dev's branch "lokal"
#                                                  # (--lokal-zurueck, --lokal-verwerfen; speech-spark lokal …)
#
# Without --to/--newest only versions whose GitHub test run ("Tests") passed are installed: main can
# carry a red commit for a while when several changes land at once.
#
# The panel's "back to the previous version" button writes the commit into
# /var/lib/speech-spark/state/update-target and starts this script; only commits that are part
# of the official branch are accepted.
#
# Works on the installer's own clone in /opt/speech-spark/src. Your settings in
# /etc/speech-spark stay. If the new version fails before it goes live (downloads, packages,
# self-test), the running services are left untouched and the clone goes back to the old version.
# If it fails after that, the previous version is installed again.
#
# Local changes are never lost (Entwickeln auf dem Pi, app/entwickeln.py, Dominik 2026-11-03): with local commits
# installed, an update puts them on the new green main (commits already on main drop out) and quick-tests them in a
# sandbox; on a conflict or a red test the running version stays and the panel says so. Uncommitted edits in the
# clone are kept as a patch next to it before anything is reset. Local commits are not upstream code: GitHub's
# green run and the signature check below vouch only for main; entwickeln.py checks the local ones itself, and the
# version shows "+lokal". None of them ever runs as root (install.sh's self-test is the sandbox's quick test then).
set -euo pipefail

SRC=${SPEECH_SPARK_SRC:-/opt/speech-spark/src}
BRANCH=main
# no way back to before this commit from the panel (V01.0.75: root no longer runs config values)
SECURITY_FLOOR=7373d1a3bb8df864631ec1f722b839b86e445cdb
CHECK=0
TESTED=0
TARGET=""
NEWEST=0
[ "${1:-}" = --check ] && CHECK=1
[ "${1:-}" = --newest ] && NEWEST=1
[ "${1:-}" = --to ] && TARGET=${2:-}
LOKAL_ART=""   # einspielen | zurueck | verwerfen (the panel's wish or the command line), aufsetzen (an update)
case "${1:-}" in --lokal) LOKAL_ART=einspielen ;; --lokal-zurueck) LOKAL_ART=zurueck ;; --lokal-verwerfen) LOKAL_ART=verwerfen ;; esac
STATE=${SPEECH_SPARK_STATE:-/var/lib/speech-spark/state}
[ "$(id -u)" = 0 ] || { echo "run with sudo" >&2; exit 1; }
# the state folder belongs to the service user: root reads and writes there only as that user, so a link
# planted there never makes root read (or write) a file of its own
as_svc() { runuser -u speech -- "$@"; }
# Progress for the panel (step, text, done + ok at the end). The panel writes the first step at the click
# (update.begin: "Sicherung vor dem Update") and holds the lock from then on; every step here keeps its start time,
# and every way this script ends, early ones included, writes done + ok with the reason, which releases the lock.
# install.sh adds one step per section it starts.
export SPEECH_SPARK_PROGRESS=${SPEECH_SPARK_PROGRESS:-$STATE/update-progress.json}
newver=""
step() {  # text: one step of this update; the start time stays the one the panel wrote (numbers only, under 30 min)
  [ "$CHECK" = 1 ] && return 0
  local now s
  now=$(date +%s)
  s=$(as_svc cat -- "$SPEECH_SPARK_PROGRESS" 2>/dev/null | jq -r 'if .done == false then .started else empty end' 2>/dev/null \
    | tr -dc '0-9' | head -c 12 || true)
  { [ -n "$s" ] && [ "$s" -le "$now" ] && [ $((now - s)) -lt 1800 ]; } || s=$now
  rm -rf -- "$SPEECH_SPARK_PROGRESS" "$SPEECH_SPARK_PROGRESS.tmp"
  jq -nc --argjson now "$now" --argjson s "$s" --arg t "$1" --arg v "$newver" \
    '{step: 1, text: $t, started: $s, updated: $now, done: false, ok: null, version: $v}' \
    | as_svc tee -- "$SPEECH_SPARK_PROGRESS" >/dev/null || true
}
finish() {  # ok message
  [ "$CHECK" = 1 ] && return 0
  local j
  j=$(as_svc cat -- "$SPEECH_SPARK_PROGRESS" | jq -c --argjson ok "$1" --arg t "$2" --argjson now "$(date +%s)" \
    '.done=true | .ok=$ok | .text=$t | .updated=$now') \
    && printf '%s\n' "$j" | as_svc tee -- "$SPEECH_SPARK_PROGRESS" >/dev/null
}
# an end without its own message (a failed command under set -e): still done, with the exit code, never a lock left
on_exit() {
  local rc=$?
  [ "$CHECK" = 1 ] && return 0
  if as_svc cat -- "$SPEECH_SPARK_PROGRESS" 2>/dev/null | jq -e '.done == false' >/dev/null 2>&1; then
    finish false "Update abgebrochen (Fehler $rc); die bisherige Version läuft weiter" || true
  fi
}
trap on_exit EXIT
trap 'finish false "Update abgebrochen"; exit 143' TERM INT
stop_early() {  # message for the panel: nothing changed
  finish false "$1" || true
  exit 1
}
step "Lädt und prüft die neue Version"
FROM_PANEL=0
if [ -z "$TARGET" ] && [ -s "$STATE/update-target" ] && [ ! -L "$STATE/update-target" ]; then
  TARGET=$(as_svc head -c 64 -- "$STATE/update-target" 2>/dev/null | tr -dc '0-9a-f' || true)
  FROM_PANEL=1
fi
rm -f "$STATE/update-target"
# the panel's „Lokal einspielen“ (entwickelnseite.py): one fixed word, read as the service user
if [ -z "$LOKAL_ART" ] && [ -s "$STATE/update-lokal" ] && [ ! -L "$STATE/update-lokal" ]; then
  LOKAL_ART=$(as_svc head -c 20 -- "$STATE/update-lokal" 2>/dev/null | tr -dc 'a-z' || true)
  case "$LOKAL_ART" in einspielen|zurueck|verwerfen) TARGET=""; FROM_PANEL=0 ;; *) LOKAL_ART="" ;; esac
fi
rm -f "$STATE/update-lokal"
[ -d "$SRC/.git" ] || { echo "$SRC is not a git clone; run install.sh from a git checkout first" >&2; exit 1; }

cd "$SRC"
# Compare with what is installed, not with the clone: an aborted update can leave the
# clone ahead of the installed version.
old=$(jq -r '.commit // empty' "$(dirname "$SRC")/VERSION.json" 2>/dev/null || true)
git cat-file -e "${old:-x}^{commit}" 2>/dev/null || old=$(git rev-parse HEAD)
echo "Installed: $(git log -1 --format='%h %cs %s' "$old")"
# local changes running now (install.sh writes them into VERSION.json): their head stays reachable in this clone
ENTW="$(dirname "$SRC")/app/entwickeln.py"
old_kopf=$(jq -r '.lokal_kopf // empty' "$(dirname "$SRC")/VERSION.json" 2>/dev/null | tr -dc '0-9a-f' | head -c 40 || true)
old_n=$(jq -r '.lokal // 0' "$(dirname "$SRC")/VERSION.json" 2>/dev/null | tr -dc '0-9' | head -c 3 || true)
{ [ "${#old_kopf}" = 40 ] && [ "${old_n:-0}" -gt 0 ] && git cat-file -e "$old_kopf^{commit}" 2>/dev/null; } || { old_kopf=""; old_n=0; }
lokal_kopf=""; lokal_n=0; lokal_test=0
lokal() {  # art [new]: entwickeln.py checks, rebases and quick-tests as root without running any of it; "kopf basis n tests"
  [ -f "$ENTW" ] || { echo "Lokale Änderungen: Entwickeln auf dem Pi ist nicht installiert; nichts geändert"; return 3; }
  /usr/bin/python3 -I "$ENTW" vorbereiten "$@"
}
if [ -n "$LOKAL_ART" ]; then
  # Entwickeln auf dem Pi (Weg B): no GitHub; the main commit stays the installed one, the local commits change
  echo "Local changes ($LOKAL_ART): checking and quick test (no internet needed) ..."
  step "Lokale Änderungen werden geprüft"
  out=$(lokal "$LOKAL_ART") || stop_early "$(printf '%s' "$out" | tail -n 1 | head -c 300)"
  read -r lokal_kopf new lokal_n lokal_test <<<"$out"
  { [ "${#lokal_kopf}" = 40 ] && [ "$new" = "$old" ] && [[ "$lokal_n" =~ ^[0-9]{1,3}$ ]]; } \
    || stop_early "Lokale Änderungen: unerwartete Antwort; nichts geändert"
else
echo "Fetching $(git remote get-url origin) ($BRANCH) ..."
git fetch --quiet origin "$BRANCH" || { echo "GitHub not reachable: the new version could not be fetched; nothing changed." >&2
  stop_early "Neue Version konnte nicht geladen werden (GitHub nicht erreichbar); die bisherige Version läuft weiter"; }
new=$(git rev-parse "origin/$BRANCH")

# newest commit of $BRANCH whose "Tests" run passed (JSON of the Actions API on stdin)
green_commit() {
  jq -r --arg b "$BRANCH" '[.workflow_runs[]? | select(.head_branch == $b and .conclusion == "success")
    | .head_sha][0] // empty' 2>/dev/null | tr -dc '0-9a-f' | head -c 40
}
if [ -z "$TARGET" ] && [ "$NEWEST" = 0 ]; then
  url=$(git remote get-url origin)
  if [[ "$url" =~ ^(https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/?$ ]]; then
    repo=${BASH_REMATCH[2]%.git}
    runs="https://api.github.com/repos/$repo/actions/workflows/tests.yml/runs?branch=$BRANCH&event=push"
    green=$(curl -fsS --max-time 20 -H "Accept: application/vnd.github+json" "$runs&per_page=30" \
      | green_commit || true)
    # many pushes in a row cancel each other's runs: then the newest 30 hold no green one, ask for those directly
    [ -n "$green" ] || green=$(curl -fsS --max-time 20 -H "Accept: application/vnd.github+json" \
      "$runs&status=success&per_page=5" | green_commit || true)
    if [ "${#green}" != 40 ] || ! git cat-file -e "$green^{commit}" 2>/dev/null \
        || ! git merge-base --is-ancestor "$green" "$new"; then
      echo "No version with passed GitHub tests found (GitHub not reachable?); nothing changed." >&2
      echo "To take the newest version anyway: sudo $0 --newest" >&2
      stop_early "Keine Version mit bestandenen GitHub-Tests gefunden; die bisherige Version läuft weiter"
    fi
    if [ "$green" != "$new" ]; then
      echo "The newest version $(git rev-parse --short "$new") has not passed GitHub's tests (yet); taking the newest one that did."
      new=$green
    fi
    TESTED=1  # exactly the commit GitHub's test run passed: install.sh only needs its short smoke test
  fi  # a clone from elsewhere has no GitHub test results to ask
fi
if [ -n "$TARGET" ]; then
  # only versions that are part of the official branch
  if ! git cat-file -e "$TARGET^{commit}" 2>/dev/null || ! git merge-base --is-ancestor "$TARGET" "origin/$BRANCH"; then
    echo "Version $TARGET is not part of $BRANCH; nothing changed." >&2
    stop_early "Diese Version gehört nicht zum offiziellen Stand; nichts geändert"
  fi
  new=$(git rev-parse "$TARGET")
  if [ "$FROM_PANEL" = 1 ]; then
    # The state folder belongs to the service user, so this file is no proof the admin asked for it:
    # accept only the version root itself kept as "previous", and never one from before the
    # security fixes (an old install.sh ran config values as commands, as root).
    prev=$(jq -r '.commit // empty' "$(dirname "$SRC")/VERSION.prev.json" 2>/dev/null || true)
    if [ "$new" != "$prev" ] || ! git merge-base --is-ancestor "$SECURITY_FLOOR" "$new"; then
      echo "Version $TARGET is not the previous version this Spark ran; nothing changed." >&2
      stop_early "Das ist nicht die vorige Version dieses Sparks; nichts geändert"
    fi
  fi
  echo "Going to the chosen version instead of the newest."
elif [ "$old" != "$new" ] && git merge-base --is-ancestor "$new" "$old"; then
  # installed is newer than the newest tested version (e.g. installed with --newest): nothing to do
  echo "Already up to date (no newer version has passed GitHub's tests)."
  finish true "Schon aktuell"
  exit 0
elif ! git merge-base --is-ancestor "$old" "$new"; then
  # the branch never loses commits; a rewritten history is not taken without being asked for
  echo "The history of $BRANCH was rewritten on GitHub (the installed version is no longer part of it); nothing changed." >&2
  echo "If that is intended: sudo $0 --to $(git rev-parse --short "$new")" >&2
  stop_early "Der Verlauf auf GitHub wurde umgeschrieben; nichts geändert"
fi
fi   # (not for local changes)

# Optional: only signed versions. With $SIGNERS (root's own file in the format of ssh-keygen's
# allowed signers) the version must be a commit signed with one of those keys.
# A signer file that is there but not root's own plain file (a link, another owner, writable by others) stops
# the update instead of quietly switching the check off.
SIGNERS=/etc/speech-spark-signers
if [ -e "$SIGNERS" ] || [ -L "$SIGNERS" ]; then
  if [ -L "$SIGNERS" ] || [ ! -f "$SIGNERS" ] || [ "$(stat -c %u "$SIGNERS")" != 0 ] \
      || [ -n "$(find "$SIGNERS" -maxdepth 0 -perm /022 2>/dev/null)" ]; then
    echo "$SIGNERS is not a plain file of root (writable only by root); nothing changed." >&2
    finish false "Signaturliste ungültig; nichts geändert" || true; exit 1   # (the block also runs alone: test_hardening)
  fi
  if ! git -c gpg.format=ssh -c gpg.ssh.allowedSignersFile="$SIGNERS" verify-commit "$new" >/dev/null 2>&1; then
    echo "Version $(git rev-parse --short "$new") is not signed with a key from $SIGNERS; nothing changed." >&2
    finish false "Neue Version ist nicht richtig signiert; nichts geändert" || true; exit 1
  fi
  echo "Signature checked ($SIGNERS)."
else
  echo "Signature check off (no $SIGNERS): only GitHub's https and the green test run vouch for this version."
fi

if [ "$old" = "$new" ] && [ -z "$LOKAL_ART" ]; then
  echo "Already up to date."
  finish true "Schon aktuell"
  exit 0
fi
if [ -z "$LOKAL_ART" ] && [ "$old" != "$new" ] && [ "$old_n" -gt 0 ]; then
  # the local changes go along onto the new version, quick-tested; never thrown away, never installed red
  echo "Putting $old_n local change(s) on the new version, then the quick test ..."
  step "Lokale Änderungen kommen auf die neue Version"
  LOKAL_ART=aufsetzen
  out=$(lokal aufsetzen "$new") || stop_early "$(printf '%s' "$out" | tail -n 1 | head -c 300)"
  read -r lokal_kopf _ lokal_n lokal_test <<<"$out"
  { [ "${#lokal_kopf}" = 40 ] && [[ "$lokal_n" =~ ^[0-9]{1,3}$ ]]; } || stop_early "Lokale Änderungen: unerwartete Antwort; nichts geändert"
  [ "$lokal_n" -gt 0 ] || echo "Every local change is part of the new version now: the branch is empty again."
fi
inst=$new; [ "$lokal_n" -gt 0 ] && inst=$lokal_kopf   # the commit whose files are installed
echo "Available: $(git log -1 --format='%h %cs %s' "$new")"
[ -n "$LOKAL_ART" ] && echo "Local changes on it: $lokal_n (never upstream code; quick test: $lokal_test module(s))"
echo "Changes:"
if git merge-base --is-ancestor "$new" "$old"; then
  echo "  (back to an older version; these changes are undone:)"
  git log --format='  %h %s' "$new..$old"
else
  git log --format='  %h %s' "$old..$new"
fi
[ "$CHECK" = 1 ] && exit 0

newver=$(git show "$new:app/VERSION" 2>/dev/null | head -1 | tr -dc 'V0-9.' | head -c 20 || true)
step "Neue Version geladen"

echo
# Spark teilen (plan raspberry-split B5): with the models on another computer that one updates first, by its own
# rules (the newest version with passed GitHub tests); this computer waits for it, then goes on either way
mhost=$(jq -r '.models.host // "127.0.0.1"' /etc/speech-spark/config.json 2>/dev/null || echo 127.0.0.1)
# (a local install changes only this computer's panel: the model computer stays as it is)
if [ "$CHECK" = 0 ] && { [ -z "$LOKAL_ART" ] || [ "$LOKAL_ART" = aufsetzen ]; } && [ -n "$mhost" ] && [ "$mhost" != 127.0.0.1 ] && [ "$mhost" != localhost ] && [ "$mhost" != ::1 ]; then
  echo "Updating the model computer first ..."
  step "Modell-Rechner wird zuerst aktualisiert"
  /usr/local/bin/speech-spark teilen modelle-update || echo "The model computer did not update; going on (two versions only give a hint)."
fi
echo "Updating ..."
# the version running now becomes "the previous version" the panel can go back to (a local install keeps it: its own
# way back is speech-spark lokal zurueck)
if [ -z "$LOKAL_ART" ] || [ "$LOKAL_ART" = aufsetzen ]; then
  [ -f "$(dirname "$SRC")/VERSION.json" ] && cp "$(dirname "$SRC")/VERSION.json" "$(dirname "$SRC")/VERSION.prev.json.new"
fi
# uncommitted edits in this clone are never thrown away silently: kept as a patch next to it (root's folder)
if ! git diff --quiet HEAD -- 2>/dev/null; then
  keep="$(dirname "$SRC")/gesichert"; install -d -m 700 "$keep"
  kept="$keep/src-$(date +%Y%m%d-%H%M%S).patch"
  git diff HEAD -- >"$kept" || true
  echo "Uncommitted changes in $SRC kept in $kept."
fi
git reset --hard --quiet "$inst"
LOKAL_ENV=()   # local commits: install.sh's self-test would run them as root, the sandbox's quick test ran instead
[ "$lokal_n" -gt 0 ] && LOKAL_ENV=(SPEECH_SPARK_NO_SELFTEST=1 SPEECH_SPARK_LOKAL_BASIS="$new" SPEECH_SPARK_LOKAL_ANZAHL="$lokal_n")
SWITCHED="$(dirname "$SRC")/.switched"
rm -f "$SWITCHED"
if env "${LOKAL_ENV[@]}" SPEECH_SPARK_TESTED=$TESTED ./install.sh --no-smoke --update; then
  rm -f "$SWITCHED"
  echo
  echo "Update finished: $(git log -1 --format='%h %s' "$new")$([ "$lokal_n" -gt 0 ] && echo " +lokal ($lokal_n)")"
  [ -f "$(dirname "$SRC")/VERSION.prev.json.new" ] && mv "$(dirname "$SRC")/VERSION.prev.json.new" "$(dirname "$SRC")/VERSION.prev.json"
  if [ -n "$LOKAL_ART" ] && [ -f "$ENTW" ]; then
    /usr/bin/python3 -I "$ENTW" fertig "$LOKAL_ART" "$inst" "$new" "$lokal_n" "${lokal_test:-0}" || echo "Local state not written."
  fi
  finish true "Fertig"
else
  rc=$?
  echo
  [ -n "$LOKAL_ART" ] && [ -f "$ENTW" ] && { /usr/bin/python3 -I "$ENTW" fehler "$LOKAL_ART" fehler || true; }
  git reset --hard --quiet "${old_kopf:-$old}"
  OLD_ENV=()
  [ "$old_n" -gt 0 ] && OLD_ENV=(SPEECH_SPARK_LOKAL_BASIS="$old" SPEECH_SPARK_LOKAL_ANZAHL="$old_n")
  rm -f "$(dirname "$SRC")/VERSION.prev.json.new"
  if [ -f "$SWITCHED" ]; then
    # the new code was already live: put the previous version back the same way
    rm -f "$SWITCHED"
    echo "UPDATE FAILED (exit $rc) after the new version went live. Installing the previous version again ..."
    # (an older install.sh does not know newer options; the environment variable it just ignores)
    if env "${OLD_ENV[@]}" SPEECH_SPARK_NO_SELFTEST=1 ./install.sh --no-smoke --update; then
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
