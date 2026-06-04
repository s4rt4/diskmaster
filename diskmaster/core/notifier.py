"""Threshold checking + desktop notifications.

:class:`Notifier.check` is pure (no I/O, no Qt) so it is unit-testable: it
compares disks against the configured thresholds and returns the alerts that are
*newly* active. State is remembered per (identity, alert_type) so a disk that
stays hot does not re-notify on every poll — it fires once on the rising edge and
clears when the condition resolves.

Delivery is best-effort: ``notify-send`` if present, otherwise an optional Qt
tray callback supplied by the UI.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable

from .models import DiskInfo, DiskType, Status

# alert_type constants
TEMP_HIGH = "TEMP_HIGH"
HEALTH_LOW = "HEALTH_LOW"
SMART_FAIL = "SMART_FAIL"


@dataclass
class Alert:
    identity: str
    device: str
    alert_type: str
    message: str


class Notifier:
    def __init__(self, settings, tray_notify: Callable[[str, str], None] | None = None):
        """``settings`` is a config.Settings; ``tray_notify(title, msg)`` is an
        optional fallback (e.g. QSystemTrayIcon.showMessage)."""
        self._settings = settings
        self._tray_notify = tray_notify
        self._active: set[tuple[str, str]] = set()  # (identity, alert_type) latched

    def set_tray_callback(self, cb: Callable[[str, str], None]) -> None:
        self._tray_notify = cb

    # ------------------------------------------------------------- threshold --

    def _temp_limit(self, disk: DiskInfo) -> int:
        key = {
            DiskType.HDD: "temp_hdd",
            DiskType.SSD: "temp_ssd",
            DiskType.NVME: "temp_nvme",
        }.get(disk.disk_type, "temp_hdd")
        return int(self._settings.get("thresholds", key, 55))

    def _health_min(self) -> int:
        return int(self._settings.get("thresholds", "health_min", 80))

    def check(self, disks: list[DiskInfo]) -> list[Alert]:
        """Return alerts that crossed into a bad state since the last call."""
        fresh: list[Alert] = []
        for d in disks:
            self._eval(d, TEMP_HIGH,
                       d.temp_current >= 0 and d.temp_current > self._temp_limit(d),
                       f"{d.device} temperature {d.temp_current}°C exceeds "
                       f"{self._temp_limit(d)}°C", fresh)
            self._eval(d, HEALTH_LOW,
                       d.health >= 0 and d.health < self._health_min(),
                       f"{d.device} health {d.health}% below "
                       f"{self._health_min()}%", fresh)
            self._eval(d, SMART_FAIL, d.status == Status.FAILURE,
                       f"{d.device} reports FAILURE status", fresh)
        return fresh

    def _eval(self, disk: DiskInfo, atype: str, bad: bool, msg: str,
              out: list[Alert]) -> None:
        key = (disk.identity, atype)
        if bad and key not in self._active:
            self._active.add(key)
            out.append(Alert(disk.identity, disk.device, atype, msg))
        elif not bad and key in self._active:
            self._active.discard(key)  # condition cleared → re-arm

    # -------------------------------------------------------------- delivery --

    def notify(self, alerts: list[Alert]) -> None:
        for a in alerts:
            self._send("DiskMaster Alert", a.message)

    def _send(self, title: str, message: str) -> None:
        ns = shutil.which("notify-send")
        if ns:
            try:
                subprocess.run([ns, "-i", "drive-harddisk", "-u", "critical",
                                title, message], check=False, timeout=5)
                return
            except (OSError, subprocess.SubprocessError):
                pass
        if self._tray_notify:
            try:
                self._tray_notify(title, message)
            except Exception:  # noqa: BLE001 — notification must never crash app
                pass


__all__ = ["Notifier", "Alert", "TEMP_HIGH", "HEALTH_LOW", "SMART_FAIL"]
