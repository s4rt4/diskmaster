"""Mounted-volume enumeration — the C:/D: free-space column.

Reads ``/proc/mounts`` for real block-device filesystems and queries free space
with ``os.statvfs``. No root needed. Each volume is mapped back to its parent
physical disk (``/dev/sda1`` → ``sda``) so the UI can show "Disk: N" like
HDSentinel.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from ..models import VolumeInfo

# Pseudo/virtual filesystems we never want to list.
_SKIP_FS = {
    "proc", "sysfs", "tmpfs", "devtmpfs", "devpts", "cgroup", "cgroup2",
    "overlay", "squashfs", "autofs", "mqueue", "debugfs", "tracefs",
    "securityfs", "pstore", "bpf", "configfs", "fusectl", "hugetlbfs",
    "binfmt_misc", "ramfs", "efivarfs", "fuse.gvfsd-fuse", "fuse.portal",
    "nsfs", "rpc_pipefs",
}


def _parent_disk(dev_name: str) -> str:
    """'sda1'->'sda', 'nvme0n1p2'->'nvme0n1', 'mmcblk0p1'->'mmcblk0'."""
    if dev_name.startswith(("nvme", "mmcblk")):
        return re.sub(r"p\d+$", "", dev_name)
    return re.sub(r"\d+$", "", dev_name)


def list_volumes() -> list[VolumeInfo]:
    """Mounted block-device filesystems with usage, sorted by mountpoint."""
    mounts = Path("/proc/mounts")
    try:
        lines = mounts.read_text().splitlines()
    except OSError:
        return []

    seen: set[str] = set()
    out: list[VolumeInfo] = []
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        dev, mountpoint, fstype = parts[0], parts[1], parts[2]
        if not dev.startswith("/dev/"):
            continue
        if fstype in _SKIP_FS:
            continue
        # Resolve symlinks (e.g. /dev/mapper, /dev/disk/by-uuid) to a real name.
        real = os.path.realpath(dev)
        name = real.rsplit("/", 1)[-1]
        if real in seen:
            continue
        seen.add(real)

        mp = mountpoint.replace("\\040", " ")
        try:
            st = os.statvfs(mp)
            total = st.f_blocks * st.f_frsize
            free = st.f_bavail * st.f_frsize
        except OSError:
            total = free = 0
        if total <= 0:
            continue

        out.append(
            VolumeInfo(
                device=real,
                mountpoint=mp,
                label=mp if mp != "/" else "/ (root)",
                fstype=fstype,
                total_gb=round(total / 1_000_000_000, 2),
                free_gb=round(free / 1_000_000_000, 2),
                parent=_parent_disk(name),
            )
        )
    out.sort(key=lambda v: v.mountpoint)
    return out


__all__ = ["list_volumes"]
