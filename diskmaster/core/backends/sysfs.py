"""I/O throughput from sysfs — no root, no waking the drive.

``/sys/block/<dev>/stat`` exposes cumulative counters (Documentation/block/stat).
Field indices we use (whitespace-separated):

    [0] reads completed   [2] sectors read     [4] writes completed
    [6] sectors written   [9] ms spent doing I/O (field 10, the busy time)

Sectors are fixed 512-byte units regardless of the device's logical block size.
Throughput is a *delta between two samples*, so :class:`IOSampler` keeps the
previous reading per device and a wall-clock timestamp.
"""
from __future__ import annotations

import time
from pathlib import Path

from ..models import IOStats

_SECTOR = 512


def _read_stat(name: str) -> list[int] | None:
    p = Path("/sys/block") / name / "stat"
    try:
        fields = p.read_text().split()
    except OSError:
        return None
    try:
        return [int(x) for x in fields]
    except ValueError:
        return None


class IOSampler:
    """Stateful: feed it device names over time; it returns rate deltas."""

    def __init__(self):
        # name -> (timestamp, sectors_read, sectors_written, busy_ms)
        self._prev: dict[str, tuple[float, int, int, int]] = {}

    def sample(self, name: str, now: float | None = None) -> IOStats | None:
        """Return throughput since the previous sample for ``name``.

        First call for a device primes the baseline and returns a zeroed
        IOStats. Returns None if the device has no readable stat file.
        """
        fields = _read_stat(name)
        if not fields or len(fields) < 10:
            return None
        now = now if now is not None else time.monotonic()
        sectors_read = fields[2]
        sectors_written = fields[6]
        busy_ms = fields[9]

        prev = self._prev.get(name)
        self._prev[name] = (now, sectors_read, sectors_written, busy_ms)
        if prev is None:
            return IOStats()

        dt = now - prev[0]
        if dt <= 0:
            return IOStats()

        read_bps = max(0, sectors_read - prev[1]) * _SECTOR / dt
        write_bps = max(0, sectors_written - prev[2]) * _SECTOR / dt
        busy_frac = max(0, busy_ms - prev[3]) / (dt * 1000.0)

        return IOStats(
            read_mbps=round(read_bps / 1_000_000, 3),
            write_mbps=round(write_bps / 1_000_000, 3),
            utilization_pct=round(min(busy_frac, 1.0) * 100, 1),
        )

    def reset(self, name: str | None = None) -> None:
        if name is None:
            self._prev.clear()
        else:
            self._prev.pop(name, None)


__all__ = ["IOSampler"]
