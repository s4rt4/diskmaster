#!/bin/sh
# Build a .deb with dpkg-deb (no full debhelper toolchain needed). Stages the
# tree via `make install`, drops in DEBIAN control + maintainer scripts.
#
#   ./build-deb.sh                # -> diskmaster_<version>_all.deb
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
command -v dpkg-deb >/dev/null 2>&1 || { echo "dpkg-deb not found" >&2; exit 1; }

VERSION=$(make -s -f "$HERE/Makefile" version)
ARCH=all
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

make -f "$HERE/Makefile" install DESTDIR="$STAGE" PREFIX=/usr

install -d "$STAGE/DEBIAN"
sed "s/@VERSION@/$VERSION/" "$HERE/debian/control" > "$STAGE/DEBIAN/control"
install -m 0755 "$HERE/debian/postinst" "$STAGE/DEBIAN/postinst"
install -m 0755 "$HERE/debian/postrm"   "$STAGE/DEBIAN/postrm"

OUT="${1:-$HERE/diskmaster_${VERSION}_${ARCH}.deb}"
dpkg-deb --root-owner-group --build "$STAGE" "$OUT"
echo "Built $OUT"
