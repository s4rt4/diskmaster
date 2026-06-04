"""DiskService — orchestrates non-privileged sysfs data with privileged
HDSentinel/smartctl data behind one API the UI/poller can call.
"""
from __future__ import annotations

from . import paths
from .backends import nvme as nvme_backend
from .backends.smartctl import is_asleep, parse_smart_json, power_mode_from_json
from .backends.sysfs import IOSampler
from .backends.volumes import list_volumes
from .models import DiskInfo, DiskType, IOStats, VolumeInfo
from .parser.hdsentinel_solid import SolidRow, parse_solid
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

    def volumes(self) -> list[VolumeInfo]:
        """Mounted volumes with free space — non-privileged."""
        return list_volumes()

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

    def quick_scan(self) -> dict[str, SolidRow]:
        """Lightweight `-solid` poll → {device: SolidRow} of temp/health/POH.

        Cheaper than a full XML scan; used between full scans to keep temp and
        health fresh. Returns an empty dict if the output can't be parsed.
        """
        self.ensure_helper()
        text = self.client.hdsentinel_solid()
        return {row.device: row for row in parse_solid(text, with_interface=False)}

    def load_smart(self, device: str, nowake: bool = False):
        """Return (list[SmartAttribute], raw_json) for a device.

        With ``nowake`` the read is skipped (no spin-up) if the drive is asleep;
        the raw dict then carries ``{"_standby": True}`` and the attr list is
        empty.
        """
        self.ensure_helper()
        data = self.client.smart(device, nowake=nowake)
        if nowake and is_asleep(data):
            return [], {"_standby": True}
        return parse_smart_json(data), data

    def power_mode(self, device: str) -> str:
        """ATA power mode of a drive without waking it (active/idle/standby/…)."""
        self.ensure_helper()
        return power_mode_from_json(self.client.power_mode(device))

    def all_disks_asleep(self) -> bool:
        """True iff every spinning/SATA disk is in standby/sleep.

        NVMe drives have no ATA standby and are ignored. With no ATA disks at
        all this is False (there is nothing whose sleep we'd be preserving).
        """
        ata = [d for d in self.sysfs_disks()
               if d.disk_type in (DiskType.HDD, DiskType.SSD)]
        if not ata:
            return False
        for d in ata:
            try:
                if self.power_mode(d.device) not in ("standby", "sleep"):
                    return False
            except PrivError:
                return False  # can't tell → don't suppress the scan
        return True

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
