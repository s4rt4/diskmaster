"""DiskService — orchestrates non-privileged sysfs data with privileged
HDSentinel/smartctl data behind one API the UI/poller can call.
"""
from __future__ import annotations

from . import paths
from .backends.smartctl import parse_smart_json
from .models import DiskInfo, DiskType
from .parser.hdsentinel_xml import HDSentinelParseError, parse_xml
from .privclient import PrivClient, PrivError


class DiskService:
    def __init__(self, client: PrivClient | None = None):
        self.client = client or PrivClient()

    # -- non-privileged: always available, instant ----------------------------

    def sysfs_disks(self) -> list[DiskInfo]:
        """Disk skeletons from sysfs — shown immediately, before auth."""
        out = []
        for name in paths.physical_block_devices():
            meta = paths.sysfs_disk_meta(name)
            out.append(
                DiskInfo(
                    device=meta["device"],
                    model=meta["model"],
                    size_gb=meta["size_gb"],
                    disk_type=DiskType(meta["disk_type"]),
                )
            )
        return out

    # -- privileged: needs the helper (pkexec auth) ---------------------------

    def ensure_helper(self) -> None:
        if not self.client.is_alive():
            self.client.start()

    def full_scan(self) -> list[DiskInfo]:
        """Full HDSentinel scan, enriched with sysfs type/size fallbacks."""
        self.ensure_helper()
        xml = self.client.hdsentinel_xml()
        disks = parse_xml(xml)  # raises HDSentinelParseError on bad output
        self._enrich_from_sysfs(disks)
        return disks

    def _enrich_from_sysfs(self, disks: list[DiskInfo]) -> None:
        sysfs = {d.device: d for d in self.sysfs_disks()}
        for disk in disks:
            ref = sysfs.get(disk.device)
            if not ref:
                continue
            if disk.disk_type == DiskType.UNKNOWN:
                disk.disk_type = ref.disk_type
            if disk.size_gb <= 0:
                disk.size_gb = ref.size_gb
            if not disk.model:
                disk.model = ref.model

    def load_smart(self, device: str):
        """Return (list[SmartAttribute], raw_json) for a device."""
        self.ensure_helper()
        data = self.client.smart(device)
        return parse_smart_json(data), data

    def close(self) -> None:
        self.client.close()


__all__ = ["DiskService", "PrivError", "HDSentinelParseError"]
