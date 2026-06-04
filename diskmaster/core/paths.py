"""Binary discovery + physical block-device enumeration.

No root required. Used by both the GUI side and the privileged helper so the
helper resolves the same binaries the user configured.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

# sbin dirs are frequently absent from a desktop user's PATH; sweep them too.
_SEARCH_DIRS = [
    "/usr/local/sbin",
    "/usr/local/bin",
    "/usr/sbin",
    "/sbin",
    "/usr/bin",
    "/bin",
]

# Virtual / non-physical block devices to hide from the dashboard.
_EXCLUDE_PREFIXES = ("loop", "dm-", "sr", "zram", "ram", "md", "fd", "nbd")


def find_binary(name: str, extra_dirs: list[str] | None = None) -> str | None:
    """Locate an executable, checking PATH first then common sbin/bin dirs."""
    found = shutil.which(name)
    if found:
        return found
    for d in (extra_dirs or []) + _SEARCH_DIRS:
        cand = Path(d) / name
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


def find_hdsentinel(app_dir: str | None = None) -> str | None:
    """Prefer a bundled binary (portable mode), then PATH/sbin sweep."""
    names = ["hdsentinel", "HDSentinel"]
    search_roots = []
    if app_dir:
        search_roots += [Path(app_dir), Path(app_dir) / "assets"]
    for root in search_roots:
        for n in names:
            cand = root / n
            if cand.is_file() and os.access(cand, os.X_OK):
                return str(cand)
    for n in names:
        p = find_binary(n)
        if p:
            return p
    return None


def find_smartctl() -> str | None:
    return find_binary("smartctl")


def find_nvme() -> str | None:
    return find_binary("nvme")


def _read_sysfs(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def physical_block_devices() -> list[str]:
    """Sorted device names of physical disks, e.g. ['nvme0n1', 'sda', 'sdb']."""
    base = Path("/sys/block")
    if not base.exists():
        return []
    names = []
    for entry in base.iterdir():
        name = entry.name
        if name.startswith(_EXCLUDE_PREFIXES):
            continue
        names.append(name)
    return sorted(names)


def sysfs_disk_meta(name: str) -> dict:
    """User-readable disk metadata from sysfs (no root, no waking the drive)."""
    base = Path("/sys/block") / name
    rotational = _read_sysfs(base / "queue" / "rotational")
    sectors = _read_sysfs(base / "size")
    removable = _read_sysfs(base / "removable")
    model = _read_sysfs(base / "device" / "model")

    if name.startswith("nvme"):
        disk_type = "NVMe"
    elif rotational == "0":
        disk_type = "SSD"
    elif rotational == "1":
        disk_type = "HDD"
    else:
        disk_type = "Unknown"

    size_gb = 0.0
    if sectors.isdigit():
        size_gb = int(sectors) * 512 / 1_000_000_000  # 512-byte sectors

    return {
        "device": f"/dev/{name}",
        "name": name,
        "disk_type": disk_type,
        "size_gb": round(size_gb, 2),
        "removable": removable == "1",
        "model": model,
    }
