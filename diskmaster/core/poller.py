"""Background polling worker (QThread).

Runs HDSentinel scans off the GUI thread and pushes results back via signals.
A full XML scan is relatively heavy (and can wake idle disks), so it runs on the
configurable ``full_interval`` — not every few seconds. Manual refresh wakes the
loop immediately.
"""
from __future__ import annotations

import threading

from PyQt6.QtCore import QThread, pyqtSignal

from .service import DiskService
from .privclient import PrivError
from .parser.hdsentinel_xml import HDSentinelParseError


class PollerWorker(QThread):
    disks_updated = pyqtSignal(object)   # list[DiskInfo]
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, service: DiskService, interval_sec: int = 300, parent=None):
        super().__init__(parent)
        self._service = service
        self._interval = max(10, int(interval_sec))
        self._stop = threading.Event()
        self._wake = threading.Event()

    def set_interval(self, seconds: int) -> None:
        self._interval = max(10, int(seconds))
        self._wake.set()

    def refresh_now(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def run(self) -> None:  # executes in the worker thread
        while not self._stop.is_set():
            self._poll_once()
            # Sleep until interval elapses, a manual refresh, or stop.
            self._wake.wait(timeout=self._interval)
            self._wake.clear()

    def _poll_once(self) -> None:
        try:
            self.status.emit("Scanning…")
            disks = self._service.full_scan()
            self.disks_updated.emit(disks)
            self.status.emit(f"Updated — {len(disks)} disk(s)")
        except HDSentinelParseError as e:
            self.error.emit(str(e))
        except PrivError as e:
            self.error.emit(f"Privilege error: {e}")
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"{type(e).__name__}: {e}")
