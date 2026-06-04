"""DiskService — orchestrates non-privileged sysfs data with privileged
HDSentinel/smartctl data behind one API the UI/poller can call.
"""
from __future__ import annotations

from . import paths
from .backends import nvme as nvme_backend
from .backends.smartctl import parse_smart_json
from .backends.sysfs import IOSampler
from .models import DiskInfo, DiskType, IOStats
from .parser.hdsentinel_xml import HDSentinelParseError, parse_xml
from .privclient import PrivClient, PrivError


class DiskService:
    def __init__(self, client: PrivClient | None = None):
        self.client = client or PrivClient()
        self._io = IOSampler()

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
        """Full HDSentinel scan, enriched with sysfs type/size + NVMe data."""
        self.ensure_helper()
        xml = self.client.hdsentinel_xml()
        disks = parse_xml(xml)  # raises HDSentinelParseError on bad output
        self._enrich_from_sysfs(disks)
        self._add_missing_nvme(disks)
        self._attach_io_stats(disks)
        return disks

    def _add_missing_nvme(self, disks: list[DiskInfo]) -> None:
        """NVMe drives are often absent from HDSentinel output — fill them in
        from nvme-cli if available. Failures are silent (NVMe is optional)."""
        seen = {d.device for d in disks}
        for ref in self.sysfs_disks():
            if ref.disk_type != DiskType.NVME or ref.device in seen:
                continue
            try:
                data = self.client.nvme_smart(ref.device)
            except PrivError:
                continue
            nvme_backend.enrich_disk(ref, data)
            disks.append(ref)

    def _attach_io_stats(self, disks: list[DiskInfo]) -> None:
        for d in disks:
            name = d.device.rsplit("/", 1)[-1]
            stats = self._io.sample(name)
            if stats is not None:
                d.io_stats = stats

    def io_stats(self, device: str) -> IOStats | None:
        """One-off non-privileged I/O sample for a device path."""
        return self._io.sample(device.rsplit("/", 1)[-1])

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

    def start_selftest(self, device: str, ttype: str) -> dict:
        self.ensure_helper()
        return self.client.selftest_start(device, ttype)

    def selftest_log(self, device: str) -> dict:
        self.ensure_helper()
        return self.client.selftest_log(device)

    def set_aam(self, drive: str, level: str) -> dict:
        self.ensure_helper()
        return self.client.set_aam(drive, level)

    def save_report(self, name: str, fmt: str = "txt") -> str:
        """Generate a report via the helper and return its on-disk path."""
        self.ensure_helper()
        return self.client.save_report(name, fmt).get("path", "")

    def close(self) -> None:
        self.client.close()


__all__ = ["DiskService", "PrivError", "HDSentinelParseError"]
