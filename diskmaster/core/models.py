"""Data models for DiskMaster.

Pure dataclasses — no Qt, no I/O. Shared by backends, parsers, DB, and UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class DiskType(str, Enum):
    HDD = "HDD"
    SSD = "SSD"
    NVME = "NVMe"
    UNKNOWN = "Unknown"


class Status(str, Enum):
    PERFECT = "PERFECT"
    GOOD = "GOOD"
    WARNING = "WARNING"
    FAILURE = "FAILURE"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_text(cls, text: str) -> "Status":
        t = (text or "").strip().upper()
        if not t:
            return cls.UNKNOWN
        if "PERFECT" in t or "EXCELLENT" in t:
            return cls.PERFECT
        if "FAIL" in t or "CRITICAL" in t or "BACKUP" in t:
            return cls.FAILURE
        if "WARN" in t or "PROBLEM" in t or "WEAK" in t:
            return cls.WARNING
        if "GOOD" in t or "OK" in t:
            return cls.GOOD
        return cls.UNKNOWN


@dataclass
class SmartAttribute:
    attr_id: int
    name: str
    value: int
    worst: int
    threshold: int
    raw_value: int
    status: str = "OK"  # OK / WARNING / FAILED


@dataclass
class IOStats:
    read_mbps: float = 0.0
    write_mbps: float = 0.0
    utilization_pct: float = 0.0


@dataclass
class DiskInfo:
    device: str                       # /dev/sda
    model: str = ""
    serial: str = ""
    wwn: str = ""                     # fallback identity when serial is empty/dup
    firmware: str = ""
    size_gb: float = 0.0
    disk_type: DiskType = DiskType.UNKNOWN
    health: int = -1                  # 0-100, -1 = unknown
    performance: int = -1             # 0-100, -1 = unknown
    temp_current: int = -1            # °C, -1 = unknown
    temp_max: int = -1
    power_on_hours: int = -1
    estimated_lifetime: str = ""
    status: Status = Status.UNKNOWN
    total_written_bytes: int = -1     # lifetime host bytes written, -1 = unknown
    total_read_bytes: int = -1        # lifetime host bytes read, -1 = unknown
    smart_attributes: list[SmartAttribute] = field(default_factory=list)
    io_stats: IOStats | None = None

    @property
    def identity(self) -> str:
        """Stable key for history/DB. Serial preferred, WWN fallback, device last."""
        return self.serial or self.wwn or self.device

    @staticmethod
    def _human_bytes(n: int) -> str:
        """Decimal (TB/GB) like the rest of the app. '—' for unknown."""
        if n < 0:
            return "—"
        tb = n / 1_000_000_000_000
        if tb >= 1:
            return f"{tb:.2f} TB"
        return f"{n / 1_000_000_000:.1f} GB"

    @property
    def total_written_human(self) -> str:
        return self._human_bytes(self.total_written_bytes)

    @property
    def total_read_human(self) -> str:
        return self._human_bytes(self.total_read_bytes)

    @property
    def size_human(self) -> str:
        if self.size_gb <= 0:
            return "?"
        if self.size_gb >= 1024:
            return f"{self.size_gb / 1024:.2f} TB"
        return f"{self.size_gb:.0f} GB"


@dataclass
class DiskHistory:
    identity: str
    timestamp: datetime
    temp: int
    health: int
    performance: int = -1


@dataclass
class VolumeInfo:
    """A mounted filesystem on a physical disk (the C:/D: column)."""
    device: str           # /dev/sda1
    mountpoint: str       # /
    label: str            # human label (mountpoint or fs label)
    fstype: str = ""
    total_gb: float = 0.0
    free_gb: float = 0.0
    parent: str = ""      # parent disk name, e.g. 'sda'

    @property
    def used_gb(self) -> float:
        return max(0.0, self.total_gb - self.free_gb)

    @property
    def free_fraction(self) -> float:
        return self.free_gb / self.total_gb if self.total_gb > 0 else 0.0

    @property
    def used_fraction(self) -> float:
        return 1.0 - self.free_fraction if self.total_gb > 0 else 0.0

    @staticmethod
    def _human(gb: float) -> str:
        if gb >= 1024:
            return f"{gb / 1024:.2f} TB"
        return f"{gb:.1f} GB"

    @property
    def total_human(self) -> str:
        return self._human(self.total_gb)

    @property
    def free_human(self) -> str:
        return self._human(self.free_gb)

    @property
    def used_human(self) -> str:
        return self._human(self.used_gb)
