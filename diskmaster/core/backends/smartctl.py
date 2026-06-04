"""Parse smartctl -a -j JSON into SmartAttribute records."""
from __future__ import annotations

from ..models import SmartAttribute


def parse_smart_json(data: dict) -> list[SmartAttribute]:
    """Extract the ATA SMART attribute table. Empty list for NVMe/unsupported."""
    attrs: list[SmartAttribute] = []
    table = (
        data.get("ata_smart_attributes", {}).get("table", [])
        if isinstance(data, dict)
        else []
    )
    for row in table:
        raw = row.get("raw", {})
        raw_val = raw.get("value", 0)
        if isinstance(raw_val, str):
            try:
                raw_val = int(raw_val.split()[0])
            except (ValueError, IndexError):
                raw_val = 0
        value = row.get("value", 0)
        thresh = row.get("thresh", 0)
        worst = row.get("worst", 0)
        status = "OK"
        if isinstance(thresh, int) and thresh > 0 and isinstance(value, int):
            if value <= thresh:
                status = "FAILED"
            elif value <= thresh + 10:
                status = "WARNING"
        attrs.append(
            SmartAttribute(
                attr_id=row.get("id", 0),
                name=row.get("name", ""),
                value=value,
                worst=worst,
                threshold=thresh,
                raw_value=raw_val if isinstance(raw_val, int) else 0,
                status=status,
            )
        )
    return attrs


def overall_health(data: dict) -> str | None:
    """smartctl overall SMART health assessment: 'PASSED' / 'FAILED' / None."""
    status = data.get("smart_status") if isinstance(data, dict) else None
    if isinstance(status, dict):
        return "PASSED" if status.get("passed") else "FAILED"
    return None
