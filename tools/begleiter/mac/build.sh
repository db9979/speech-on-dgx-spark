#!/bin/bash
# Builds "Spark-Begleiter.app" (universal: arm64 + x86_64) with the Xcode command line tools only:
#   tools/begleiter/mac/build.sh            -> tools/begleiter/mac/build/Spark-Begleiter.app (ad-hoc signed)
# SIGN_IDENTITY="Developer ID Application: …" signs with that certificate and the hardened runtime instead.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
out="$here/build"
app="$out/Spark-Begleiter.app"
min="13.0"

# version from app/VERSION ("V01.0.339" -> "1.0.339")
raw=$(tr -d '[:space:]' < "$root/app/VERSION" 2>/dev/null || true)
ver=$(printf '%s' "$raw" | sed -E 's/^[vV]//' | awk -F. '{ for (i = 1; i <= NF; i++) { $i = $i + 0 } ; print }' OFS=.)
[[ "$ver" =~ ^[0-9]+(\.[0-9]+){0,2}$ ]] || ver="0.0.0"
build="${GITHUB_RUN_NUMBER:-${ver##*.}}"
[[ "$build" =~ ^[0-9]+$ ]] || build="0"

sdk=$(xcrun --sdk macosx --show-sdk-path)
rm -rf "$out"
mkdir -p "$out/obj" "$app/Contents/MacOS" "$app/Contents/Resources"

for arch in arm64 x86_64; do
  echo "== swiftc $arch"
  xcrun --sdk macosx swiftc \
    -sdk "$sdk" \
    -target "$arch-apple-macos$min" \
    -swift-version 5 \
    -O -whole-module-optimization \
    -parse-as-library \
    -module-name SparkBegleiter \
    -o "$out/obj/Spark-Begleiter-$arch" \
    "$here"/Sources/*.swift
done
lipo -create "$out/obj/Spark-Begleiter-arm64" "$out/obj/Spark-Begleiter-x86_64" \
  -output "$app/Contents/MacOS/Spark-Begleiter"
lipo -info "$app/Contents/MacOS/Spark-Begleiter"

cp "$here/Info.plist" "$app/Contents/Info.plist"
plutil -replace CFBundleShortVersionString -string "$ver" "$app/Contents/Info.plist"
plutil -replace CFBundleVersion -string "$build" "$app/Contents/Info.plist"
plutil -lint "$app/Contents/Info.plist"
printf 'APPL????' > "$app/Contents/PkgInfo"

if [[ -n "${SIGN_IDENTITY:-}" && "${SIGN_IDENTITY}" != "-" ]]; then
  codesign --force --timestamp --options runtime --entitlements "$here/Begleiter.entitlements" \
    --sign "$SIGN_IDENTITY" "$app"
else
  codesign --force --sign - "$app"
fi
codesign --verify --strict --verbose=2 "$app"
echo "== $app ($ver, build $build)"
