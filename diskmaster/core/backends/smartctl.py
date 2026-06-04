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


# Low-power modes in which we must NOT read SMART (it would spin the drive up).
_ASLEEP = ("standby", "sleep")


def power_mode_from_json(data: dict) -> str:
    """Read the drive power mode from a ``smartctl -n standby`` JSON result.

    When ``-n standby`` is given and the drive is asleep, smartctl issues only a
    CHECK POWER MODE command (which never spins the platters up), then prints a
    message like ``Device is in STANDBY mode, exit(2)`` and sets bit 1 of its
    exit status. We parse that out; anything else means smartctl went on to read
    the drive, i.e. it was awake.

    Returns one of ``active`` / ``idle`` / ``standby`` / ``sleep`` / ``unknown``.
    """
    if not isinstance(data, dict):
        return "unknown"
    sm = data.get("smartctl", {}) if isinstance(data.get("smartctl"), dict) else {}
    for msg in sm.get("messages", []) or []:
        text = (msg.get("string", "") if isinstance(msg, dict) else str(msg)).lower()
        for mode in ("standby", "sleep", "idle", "active"):
            if f"in {mode} mode" in text or f"is in {mode}" in text:
                return mode
    # No low-power notice and smartctl carried on → the drive answered, awake.
    exit_status = sm.get("exit_status")
    if exit_status is not None and not (int(exit_status) & 0x02):
        return "active"
    return "unknown"


def is_asleep(data: dict) -> bool:
    """True if the drive is in a mode where reading SMART would wake it."""
    return power_mode_from_json(data) in _ASLEEP
