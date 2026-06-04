#!/bin/sh
# Build a portable tarball: the app staged under a /usr prefix plus an
# install.sh that copies it into the real root. Lets users try DiskMaster
# without a distro package.
#
#   ./build-tarball.sh            # -> diskmaster-<version>.tar.gz
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
VERSION=$(make -s -f "$HERE/Makefile" version)
PKG="diskmaster-$VERSION"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

DEST="$STAGE/$PKG"
make -f "$HERE/Makefile" install DESTDIR="$DEST/root" PREFIX=/usr

# A tiny installer/uninstaller the user runs as root after extracting.
cat > "$DEST/install.sh" <<'SH'
#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
[ "$(id -u)" -eq 0 ] || { echo "Run as root: sudo ./install.sh" >&2; exit 1; }
cp -a "$HERE/root/." /
command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && \
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
echo "DiskMaster installed. Launch with: diskmaster"
echo "Note: install the HDSentinel CLI separately to enable that backend."
SH
chmod 0755 "$DEST/install.sh"

cat > "$DEST/uninstall.sh" <<'SH'
#!/bin/sh
set -eu
[ "$(id -u)" -eq 0 ] || { echo "Run as root: sudo ./uninstall.sh" >&2; exit 1; }
rm -rf /usr/lib/diskmaster /usr/libexec/diskmaster
rm -f  /usr/bin/diskmaster \
       /usr/share/polkit-1/actions/com.diskmaster.policy \
       /usr/share/applications/diskmaster.desktop \
       /usr/share/icons/hicolor/scalable/apps/diskmaster.svg
echo "DiskMaster removed."
SH
chmod 0755 "$DEST/uninstall.sh"

OUT="${1:-$HERE/$PKG.tar.gz}"
tar -C "$STAGE" -czf "$OUT" "$PKG"
echo "Built $OUT"
