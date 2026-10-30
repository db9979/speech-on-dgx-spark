#!/usr/bin/env bash
# guacd for Fernzugang → Bildschirm (app/panel/fernbild.py), built on this computer from Apache's source.
# Debian 12/13 and Raspberry Pi OS have no guacd package any more (guacamole-server left Debian in 2024), so the
# panel's computer builds the one pinned release itself (fernbild.GUACD_VERSION, checked against fernbild.GUACD_SHA256,
# fetched only from Apache's own servers), with VNC and RDP only (no SSH, telnet, Kubernetes, sound or recordings).
# The build runs as nobody in a fresh folder under /var/tmp; only the finished files go to the target as root.
# A target that already holds this release is left as it is.
#
#   guacd-bauen.sh ZIEL          (as root, from install.sh; ZIEL e.g. /opt/speech-spark/guacd)
#   guacd-bauen.sh --pakete      (prints the packages it would install for building, nothing else)
#
# The last line is always "guacd-bauen: ERGEBNIS <word>": ok, vorhanden, or why it failed (abhaengigkeiten, laden,
# pruefsumme, configure, bauen, installieren); install.sh keeps that word for the panel (fernbild.BAU_GRUENDE).
set -uo pipefail
HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIN="$HIER/panel/fernbild.py"
V=$(sed -n 's/^GUACD_VERSION = "\([0-9][0-9.]*\)"$/\1/p' "$PIN")
SHA=$(sed -n 's/^GUACD_SHA256 = "\([0-9a-f]\{64\}\)"$/\1/p' "$PIN")
ende() { echo "guacd-bauen: ERGEBNIS $1"; [ "$1" = ok ] || [ "$1" = vorhanden ]; exit $?; }
[ -n "$V" ] && [ -n "$SHA" ] || { echo "guacd-bauen: fernbild.py names no guacd release"; ende laden; }

# what building needs: the compiler (build-essential, already there from install.sh), cairo, JPEG, PNG, WebP and
# uuid for guacd itself, libvncserver for VNC, FreeRDP for RDP: FreeRDP 3 where the system has it (Debian 13,
# Ubuntu 24.04), else FreeRDP 2 (Debian 12)
pakete() {
  local rdp=freerdp2-dev
  apt-cache show freerdp3-dev >/dev/null 2>&1 && rdp=freerdp3-dev
  echo "build-essential pkg-config libtool-bin libcairo2-dev libjpeg-dev libpng-dev libwebp-dev uuid-dev libvncserver-dev $rdp"
}
if [ "${1:-}" = --pakete ]; then pakete; exit 0; fi
ZIEL="${1:?target folder}"
case "$ZIEL" in /*) ;; *) echo "guacd-bauen: the target must be an absolute path"; ende installieren ;; esac
STAND="$V $SHA"
if [ -x "$ZIEL/sbin/guacd" ] && [ "$(cat "$ZIEL/.gebaut" 2>/dev/null)" = "$STAND" ]; then
  echo "guacd-bauen: guacd $V is already there"; ende vorhanden
fi

echo "guacd-bauen: packages for building guacd $V"
# shellcheck disable=SC2046  # the package list, split on purpose
DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=300 install -y -q --no-install-recommends $(pakete) \
  || { apt-get -o DPkg::Lock::Timeout=300 update -q && \
       DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=300 install -y -q --no-install-recommends $(pakete); } \
  || ende abhaengigkeiten

BAU=$(mktemp -d /var/tmp/guacd-bau.XXXXXX) || ende bauen
trap 'rm -rf -- "$BAU"' EXIT
chown nobody "$BAU" && chmod 700 "$BAU" || ende bauen
als() { runuser -u nobody -- env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin HOME="$BAU" LC_ALL=C "$@"; }
TAR="guacamole-server-$V.tar.gz"
echo "guacd-bauen: fetching $TAR from apache.org"
ok=0
for u in "https://downloads.apache.org/guacamole/$V/source/$TAR" "https://archive.apache.org/dist/guacamole/$V/source/$TAR"; do
  if als curl -fsSL --proto '=https' --tlsv1.2 --max-time 600 -o "$BAU/$TAR" "$u"; then ok=1; break; fi
done
[ "$ok" = 1 ] || ende laden
echo "$SHA  $BAU/$TAR" | sha256sum -c --quiet - >/dev/null 2>&1 || { echo "guacd-bauen: wrong SHA-256, nothing built"; ende pruefsumme; }
als tar -xzf "$BAU/$TAR" -C "$BAU" || ende pruefsumme
SRC="$BAU/guacamole-server-$V"
echo "guacd-bauen: configure (VNC and RDP only)"
( cd "$SRC" && als ./configure --prefix="$ZIEL" --disable-static --disable-guacenc --disable-guaclog \
    --with-vnc --with-rdp --without-libssh2 --without-telnet --without-websockets --without-pango \
    --without-pulse --without-vorbis --without-ssl --without-libavcodec --without-libavformat \
    --without-libavutil --without-libswscale CFLAGS="-O2 -Wno-error" >"$BAU/configure.log" 2>&1 ) \
  || { tail -n 30 "$BAU/configure.log"; ende configure; }
grep -Eq '^ *RDP \.+ yes' "$BAU/configure.log" && grep -Eq '^ *VNC \.+ yes' "$BAU/configure.log" \
  || { grep -E 'RDP|VNC' "$BAU/configure.log" | tail -n 4; echo "guacd-bauen: VNC or RDP missing"; ende configure; }
grep -E '^ *(RDP|VNC|FreeRDP|freerdp)' "$BAU/configure.log" || true
grep -iE 'checking .*(freerdp|rdp)' "$BAU/configure.log" | head -n 60 || true
sed -n '/whether freerdp structs have a context/,/^configure:[0-9]*: result/p' "$SRC/config.log" | head -n 60 || true
echo "guacd-bauen: building with $(nproc) cores (on a Raspberry Pi 5 about 10 to 15 minutes)"
t0=$(date +%s)
( cd "$SRC" && als nice -n 10 make -j "$(nproc)" >"$BAU/make.log" 2>&1 ) \
  || { grep -m 40 -iE 'error' "$BAU/make.log"; grep -iE 'freerdp|rdp' "$SRC/config.h" | head -n 40; ende bauen; }
( cd "$SRC" && als make install DESTDIR="$BAU/stage" >"$BAU/install.log" 2>&1 ) || { tail -n 20 "$BAU/install.log"; ende installieren; }
echo "guacd-bauen: built in $(( $(date +%s) - t0 )) s"
NEU="$ZIEL.neu"
mkdir -p -- "$(dirname "$ZIEL")" && rm -rf -- "$NEU" && cp -a -- "$BAU/stage$ZIEL" "$NEU" || ende installieren
rm -rf -- "$NEU/include" "$NEU/share" "$NEU/lib/pkgconfig"; find "$NEU" -name '*.la' -delete
chown -R root:root "$NEU" && chmod -R go-w "$NEU" || ende installieren
[ -x "$NEU/sbin/guacd" ] && ls "$NEU"/lib/libguac-client-vnc.so* "$NEU"/lib/libguac-client-rdp.so* >/dev/null 2>&1 \
  || { echo "guacd-bauen: the build left no guacd with VNC and RDP"; ende installieren; }
LD_LIBRARY_PATH="$NEU/lib" "$NEU/sbin/guacd" -v >/dev/null 2>&1 || { echo "guacd-bauen: the new guacd does not start"; ende installieren; }
printf '%s\n' "$STAND" >"$NEU/.gebaut"
rm -rf -- "$ZIEL" && mv -- "$NEU" "$ZIEL" || ende installieren
echo "guacd-bauen: guacd $V in $ZIEL"
ende ok
