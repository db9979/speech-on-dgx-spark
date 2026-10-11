#!/usr/bin/env bash
# Signs update manifests with Ed25519 for the Spark (app/panel/signatur.py):
#   UPDATE_SIGNING_KEY="<PEM of the private key>" tools/sign-manifest.sh dist/begleiter.json [more files]
# writes <file>.sig (base64 of the 64 raw signature bytes) next to each file and checks it at once with the
# public key derived from the private one. The key comes only from the environment (GitHub environment
# "release", main only); it is written to a private temporary file and removed again. OPENSSL may name an
# OpenSSL 3 binary (macOS: the one from Homebrew; LibreSSL cannot sign Ed25519 raw input).
set -euo pipefail
OPENSSL=${OPENSSL:-openssl}
[ -n "${UPDATE_SIGNING_KEY:-}" ] || { echo "UPDATE_SIGNING_KEY is empty" >&2; exit 1; }
[ "$#" -gt 0 ] || { echo "usage: $0 file..." >&2; exit 2; }
umask 077
dir=$(mktemp -d)
trap 'rm -rf -- "$dir"' EXIT
printf '%s\n' "$UPDATE_SIGNING_KEY" > "$dir/key.pem"
"$OPENSSL" pkey -in "$dir/key.pem" -noout -text 2>/dev/null | grep -q 'ED25519' \
  || { echo "UPDATE_SIGNING_KEY is not an Ed25519 private key" >&2; exit 1; }
"$OPENSSL" pkey -in "$dir/key.pem" -pubout -out "$dir/pub.pem"
echo "public key (signatur.KEYS): $("$OPENSSL" pkey -pubin -in "$dir/pub.pem" -outform DER | tail -c 32 | "$OPENSSL" base64 -A)"
for f in "$@"; do
  [ -f "$f" ] && [ ! -L "$f" ] || { echo "$f: not a plain file" >&2; exit 1; }
  "$OPENSSL" pkeyutl -sign -inkey "$dir/key.pem" -rawin -in "$f" -out "$dir/sig.bin"
  "$OPENSSL" pkeyutl -verify -pubin -inkey "$dir/pub.pem" -rawin -in "$f" -sigfile "$dir/sig.bin" >/dev/null
  "$OPENSSL" base64 -A -in "$dir/sig.bin" -out "$f.sig"
  echo "signed $f"
done
