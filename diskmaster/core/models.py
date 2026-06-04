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
    smart_attributes: list[SmartAttribute] = field(default_factory=list)
    io_stats: IOStats | None = None

    @property
    def identity(self) -> str:
        """Stable key for history/DB. Serial preferred, WWN fallback, device last."""
        return self.serial or self.wwn or self.device

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
