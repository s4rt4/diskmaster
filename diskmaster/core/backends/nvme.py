"""Parse `nvme smart-log -o json` output.

nvme-cli reports the composite temperature in **kelvin** and wear as
``percentage_used`` (0 = new, 100 = rated endurance consumed). We map that onto
the same DiskInfo fields the HDSentinel path fills so the dashboard treats NVMe
drives uniformly: ``health`` ≈ ``100 - percentage_used`` (clamped).
"""
from __future__ import annotations

from ..models import DiskInfo, DiskType, Status


# NVMe reports lifetime transfer as "data units" of 1000 * 512 = 512000 bytes
# each (NVMe base spec, SMART/Health log).
_NVME_UNIT_BYTES = 512_000


def _kelvin_to_c(k) -> int:
    try:
        k = int(k)
    except (TypeError, ValueError):
        return -1
    if k <= 0:
        return -1
    return round(k - 273.15)


def parse_nvme_smart(data: dict) -> dict:
    """Extract the fields we care about from the smart-log JSON."""
    if not isinstance(data, dict):
        return {}
    used = data.get("percent_used", data.get("percentage_used"))
    return {
        "temp_c": _kelvin_to_c(data.get("temperature")),
        "available_spare": data.get("avail_spare", data.get("available_spare")),
        "percentage_used": used,
        "media_errors": data.get("media_errors"),
        "power_cycles": data.get("power_cycles"),
        "power_on_hours": data.get("power_on_hours"),
        "unsafe_shutdowns": data.get("unsafe_shutdowns"),
        "critical_warning": data.get("critical_warning"),
        "data_units_written": data.get("data_units_written"),
        "data_units_read": data.get("data_units_read"),
    }


def enrich_disk(disk: DiskInfo, data: dict) -> DiskInfo:
    """Fill an NVMe DiskInfo skeleton from smart-log data, in place."""
    s = parse_nvme_smart(data)
    if not s:
        return disk
    disk.disk_type = DiskType.NVME
    if s["temp_c"] is not None and s["temp_c"] >= 0:
        disk.temp_current = s["temp_c"]
    if isinstance(s["power_on_hours"], int):
        disk.power_on_hours = s["power_on_hours"]
    used = s["percentage_used"]
    if isinstance(used, (int, float)):
        disk.health = max(0, min(100, round(100 - used)))
    duw = s["data_units_written"]
    if isinstance(duw, int) and duw > 0:
        disk.total_written_bytes = duw * _NVME_UNIT_BYTES
    dur = s["data_units_read"]
    if isinstance(dur, int) and dur > 0:
        disk.total_read_bytes = dur * _NVME_UNIT_BYTES
    cw = s["critical_warning"]
    if isinstance(cw, int) and cw != 0:
        disk.status = Status.WARNING
    elif disk.health >= 0:
        disk.status = Status.GOOD if disk.health >= 80 else Status.WARNING
    return disk


__all__ = ["parse_nvme_smart", "enrich_disk"]
