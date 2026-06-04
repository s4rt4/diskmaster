"""Background polling worker (QThread).

Two cadences (plan §8):

* **quick** (``quick_interval``): ``hdsentinel -solid`` → just temp/health/POH,
  cheap, emitted via :attr:`quick_updated` as ``{device: SolidRow}``.
* **full** (``full_interval``): ``hdsentinel -xml`` → complete DiskInfo refresh
  (model, serial, status, SMART-ready), emitted via :attr:`disks_updated`.

The loop ticks at the quick interval and promotes a tick to a full scan once the
full interval has elapsed. A manual refresh forces a full scan immediately.
"""
from __future__ import annotations

import threading
import time

from PyQt6.QtCore import QThread, pyqtSignal

from .service import DiskService
from .privclient import PrivError
from .parser.hdsentinel_xml import HDSentinelParseError


class PollerWorker(QThread):
    disks_updated = pyqtSignal(object)   # list[DiskInfo]  (full scan)
    quick_updated = pyqtSignal(object)   # dict[str, SolidRow]  (quick scan)
    error = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, service: DiskService, full_interval_sec: int = 300,
                 quick_interval_sec: int = 30, parent=None):
        super().__init__(parent)
        self._service = service
        self._full_interval = max(30, int(full_interval_sec))
        self._quick_interval = max(5, int(quick_interval_sec))
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._force_full = False

    def set_interval(self, full_seconds: int, quick_seconds: int | None = None) -> None:
        self._full_interval = max(30, int(full_seconds))
        if quick_seconds is not None:
            self._quick_interval = max(5, int(quick_seconds))
        self._wake.set()

    def refresh_now(self) -> None:
        """Force a full scan on the next tick, immediately."""
        self._force_full = True
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def run(self) -> None:  # executes in the worker thread
        last_full = 0.0  # 0 → first iteration is always a full scan
        while not self._stop.is_set():
            now = time.monotonic()
            if self._force_full or last_full == 0.0 or \
                    now - last_full >= self._full_interval:
                self._force_full = False
                if self._full_poll():
                    last_full = time.monotonic()
            else:
                self._quick_poll()
            # Sleep until the next quick tick, a manual refresh, or stop.
            self._wake.wait(timeout=self._quick_interval)
            self._wake.clear()

    def _full_poll(self) -> bool:
        try:
            self.status.emit("Scanning…")
            disks = self._service.full_scan()
            self.disks_updated.emit(disks)
            self.status.emit(f"Updated — {len(disks)} disk(s)")
            return True
        except HDSentinelParseError as e:
            self.error.emit(str(e))
        except PrivError as e:
            self.error.emit(f"Privilege error: {e}")
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"{type(e).__name__}: {e}")
        return False

    def _quick_poll(self) -> None:
        try:
            rows = self._service.quick_scan()
            if rows:
                self.quick_updated.emit(rows)
                self.status.emit(f"Refreshed {len(rows)} disk(s)")
        except PrivError as e:
            self.error.emit(f"Privilege error: {e}")
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"{type(e).__name__}: {e}")
