#!/bin/bash
# Makes the signing key of the Android app once (only openssl needed, e.g. on the Spark or a Mac) and prints the
# two values for GitHub → Settings → Secrets and variables → Actions: ANDROID_KEYSTORE and ANDROID_KEYSTORE_PASSWORD.
# Keep ~/spark-android.p12 and ~/spark-android.pass: later app versions only install over the old one with this key.
set -euo pipefail
umask 077
out="$HOME/spark-android.p12"
if [ -e "$out" ]; then
  echo "$out gibt es schon, ich überschreibe ihn nicht (sonst passen spätere Updates nicht mehr)." >&2
  exit 1
fi
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
pw=$(openssl rand -hex 16)
openssl req -x509 -newkey rsa:4096 -nodes -keyout "$tmp/key.pem" -out "$tmp/cert.pem" -days 10000 -subj "/CN=Spark Android" 2>/dev/null
openssl pkcs12 -export -inkey "$tmp/key.pem" -in "$tmp/cert.pem" -name spark -out "$out" -passout "pass:$pw"
printf '%s\n' "$pw" > "$HOME/spark-android.pass"
b64=$(base64 < "$out" | tr -d '\n')
echo
echo "Schlüssel: $out (Passwort in ~/spark-android.pass). Beides gut aufheben."
echo
echo "In GitHub → Settings → Secrets and variables → Actions → New repository secret zwei Secrets anlegen:"
echo
echo "Name:  ANDROID_KEYSTORE_PASSWORD"
echo "Wert:  $pw"
echo
echo "Name:  ANDROID_KEYSTORE"
echo "Wert:  (die ganze nächste Zeile)"
echo "$b64"
