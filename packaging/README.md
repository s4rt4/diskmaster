# Packaging

All formats share one install definition — `packaging/Makefile`'s `install`
target — so the file layout lives in exactly one place:

| Path | Contents |
|------|----------|
| `/usr/lib/diskmaster/` | the app (main.py, `core/`, `ui/`, `config/`, `assets/`) |
| `/usr/bin/diskmaster` | user launcher → `python3 /usr/lib/diskmaster/main.py` |
| `/usr/libexec/diskmaster/diskmaster-helper` | pkexec wrapper anchored by the polkit action |
| `/usr/share/polkit-1/actions/com.diskmaster.policy` | branded auth prompt |
| `/usr/share/applications/diskmaster.desktop` | menu entry |
| `/usr/share/icons/hicolor/scalable/apps/diskmaster.svg` | app icon |

The proprietary **HDSentinel CLI is never bundled** (see `.gitignore`). smartctl
covers the core features; users install HDSentinel separately to enable that
backend.

## Build

```sh
cd packaging

./build-tarball.sh        # portable diskmaster-<ver>.tar.gz (+ install.sh)
./build-deb.sh            # diskmaster_<ver>_all.deb   (needs dpkg-deb)
# RPM:    rpmbuild -ba rpm/diskmaster.spec   (Source0 = a release tarball)
# AUR:    makepkg -si   inside aur/
# Flatpak (experimental): flatpak-builder --user --install build \
#             flatpak/com.diskmaster.DiskMaster.yml
```

Direct install without a package:

```sh
sudo make -f packaging/Makefile install     # PREFIX=/usr by default
sudo make -f packaging/Makefile uninstall
```

## Runtime dependencies

- `python3` (≥ 3.11) and `python3-pyqt6`
- `polkit` / `pkexec` (privileged helper)
- `smartmontools` (smartctl)
- optional: `nvme-cli` (NVMe SMART), `libnotify` (notifications)

## TODO before a real release

- **Flatpak** is best-effort only: a sandboxed privileged disk monitor needs
  broad host access and host-side smartmontools. Prefer the native packages.
