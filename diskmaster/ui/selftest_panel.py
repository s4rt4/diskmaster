"""Self-test runner panel.

Kicks off SMART self-tests via the privileged helper and shows the on-disk
self-test log. Extended tests can run for hours, so we never block the GUI:
both starting a test and fetching the log happen on short-lived worker threads.
Live progress isn't pushed by smartctl — the user (or the poller) refreshes the
log, which carries the latest completed runs plus the in-progress percentage.

Runs are also persisted to the history DB (:class:`HistoryDB`), so a test we
launched is remembered across app restarts: re-selecting the disk shows it as
still running, and once the drive reports the test finished we close the record.
"""
from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.db import HistoryDB
from core.models import DiskInfo
from core.service import DiskService

_LOG_COLS = ["#", "Type", "Status", "Lifetime (h)", "First error LBA"]


class _Worker(QThread):
    """Runs one DiskService call off the GUI thread."""
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn, *args, parent=None):
        super().__init__(parent)
        self._fn, self._args = fn, args

    def run(self):
        try:
            self.done.emit(self._fn(*self._args))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


class SelfTestPanel(QWidget):
    def __init__(self, service: DiskService, db: HistoryDB | None = None,
                 parent=None):
        super().__init__(parent)
        self._service = service
        self._db = db
        self._disk: DiskInfo | None = None
        self._worker: _Worker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        self.heading = QLabel("Select a disk to run self-tests.")
        self.heading.setStyleSheet("font-weight:bold;")
        root.addWidget(self.heading)

        btns = QHBoxLayout()
        self.btn_short = QPushButton("Run Short Test")
        self.btn_short.clicked.connect(lambda: self._start("short"))
        self.btn_long = QPushButton("Run Extended Test")
        self.btn_long.clicked.connect(lambda: self._start("extended"))
        self.btn_refresh = QPushButton("Refresh Log")
        self.btn_refresh.clicked.connect(self.refresh_log)
        btns.addWidget(self.btn_short)
        btns.addWidget(self.btn_long)
        btns.addWidget(self.btn_refresh)
        btns.addStretch(1)
        root.addLayout(btns)

        self.status = QLabel("")
        self.status.setStyleSheet("color:gray;")
        root.addWidget(self.status)

        self.table = QTableWidget(0, len(_LOG_COLS))
        self.table.setHorizontalHeaderLabels(_LOG_COLS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        self._set_enabled(False)

    # Back-compat: callers may still pass a device path.
    def set_device(self, device: str | None):
        self.set_disk(DiskInfo(device=device) if device else None)

    def set_disk(self, disk: DiskInfo | None):
        self._disk = disk
        self.heading.setText(
            f"Self-tests for {disk.device}" if disk else "Select a disk.")
        self._set_enabled(bool(disk))
        self.table.setRowCount(0)
        self.status.setText("")
        if disk:
            self._show_persisted_running()
            self.refresh_log()

    @property
    def _device(self) -> str | None:
        return self._disk.device if self._disk else None

    @property
    def _identity(self) -> str | None:
        return self._disk.identity if self._disk else None

    def _set_enabled(self, on: bool):
        for b in (self.btn_short, self.btn_long, self.btn_refresh):
            b.setEnabled(on)

    # ------------------------------------------------------------- actions ----

    def _start(self, ttype: str):
        if not self._device or self._busy():
            return
        self._set_enabled(False)
        self.status.setText(f"Starting {ttype} test on {self._device}…")
        self._worker = _Worker(self._service.start_selftest, self._device, ttype)
        self._worker.done.connect(lambda r, t=ttype: self._on_started(t))
        self._worker.failed.connect(self._on_error)
        self._worker.start()

    def refresh_log(self):
        if not self._device or self._busy():
            return
        self._set_enabled(False)
        self.status.setText("Reading self-test log…")
        self._worker = _Worker(self._service.selftest_log, self._device)
        self._worker.done.connect(self._on_log)
        self._worker.failed.connect(self._on_error)
        self._worker.start()

    def _busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    # ------------------------------------------------------------- handlers ---

    def _on_started(self, ttype: str):
        self._set_enabled(True)
        if self._db and self._identity:
            self._db.selftest_start(self._identity, self._device or "", ttype)
        self.status.setText(
            "Test started — extended tests take a while. Use Refresh Log to "
            "check progress.")
        self.refresh_log()

    def _on_log(self, data: dict):
        self._set_enabled(True)
        entries = self._extract_entries(data)
        self.table.setRowCount(0)
        for i, e in enumerate(entries, 1):
            r = self.table.rowCount()
            self.table.insertRow(r)
            cells = [
                str(e.get("num", i)),
                str(e.get("type", "")),
                str(e.get("status", "")),
                str(e.get("hours", "")),
                str(e.get("lba", "")),
            ]
            for c, text in enumerate(cells):
                self.table.setItem(r, c, QTableWidgetItem(text))

        progress = self._progress(data)
        self._reconcile_db(progress, entries)
        if progress is not None:
            self.status.setText(
                f"Self-test in progress — {progress}% remaining "
                f"({len(entries)} past record(s)).")
        else:
            self.status.setText(f"{len(entries)} self-test record(s).")

    def _on_error(self, err: str):
        self._set_enabled(True)
        self.status.setText("")
        QMessageBox.warning(self, "Self-test error", err)

    # --------------------------------------------------------- persistence ---

    def _show_persisted_running(self):
        """If the DB remembers a running test for this disk, surface it now."""
        if not self._db or not self._identity:
            return
        row = self._db.selftest_running(self._identity)
        if not row:
            return
        started = datetime.fromtimestamp(row["started_ts"]).strftime("%d/%m %H:%M")
        self.status.setText(
            f"{row['test_type'].title()} test started {started} is recorded as "
            "running — refreshing…")

    def _reconcile_db(self, progress: int | None, entries: list[dict]):
        """Close our DB record once the drive reports the test is no longer
        running. ``progress`` is the remaining-% (test active) or None (idle)."""
        if not self._db or not self._identity:
            return
        running = self._db.selftest_running(self._identity)
        if not running or progress is not None:
            return  # nothing open, or it's still going
        result = entries[0].get("status", "") if entries else ""
        status = "completed" if "without error" in result.lower() else (
            "error" if result else "completed")
        self._db.selftest_finish(self._identity, status, result)

    # ------------------------------------------------------------- parsing ---

    @staticmethod
    def _progress(data: dict) -> int | None:
        """Remaining percent if a self-test is running, else None."""
        if not isinstance(data, dict):
            return None
        st = (data.get("ata_smart_data", {}) or {}).get("self_test", {})
        status = (st or {}).get("status", {}) or {}
        if status.get("remaining_percent") is not None:
            return int(status["remaining_percent"])
        # Fallback: NVMe / wording-based detection.
        if "in progress" in str(status.get("string", "")).lower():
            return 0
        return None

    @staticmethod
    def _extract_entries(data: dict) -> list[dict]:
        """Normalise smartctl -l selftest -j into flat rows (newest first)."""
        if not isinstance(data, dict):
            return []
        table = (data.get("ata_smart_self_test_log", {})
                 .get("standard", {}).get("table", []))
        out = []
        for row in table:
            status = row.get("status", {})
            out.append({
                "num": row.get("num"),
                "type": (row.get("type", {}) or {}).get("string", ""),
                "status": (status or {}).get("string", ""),
                "hours": row.get("lifetime_hours", ""),
                "lba": row.get("lba_of_first_error", ""),
            })
        return out


__all__ = ["SelfTestPanel"]
