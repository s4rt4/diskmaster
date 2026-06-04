"""Self-test runner panel.

Kicks off SMART self-tests via the privileged helper and shows the on-disk
self-test log. Extended tests can run for hours, so we never block the GUI:
both starting a test and fetching the log happen on short-lived worker threads.
Live progress isn't pushed by smartctl — the user (or the poller) refreshes the
log, which carries the latest completed runs.
"""
from __future__ import annotations

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
    def __init__(self, service: DiskService, parent=None):
        super().__init__(parent)
        self._service = service
        self._device: str | None = None
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

    def set_device(self, device: str | None):
        self._device = device
        self.heading.setText(
            f"Self-tests for {device}" if device else "Select a disk.")
        self._set_enabled(bool(device))
        self.table.setRowCount(0)
        self.status.setText("")
        if device:
            self.refresh_log()

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
        self._worker.done.connect(self._on_started)
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

    def _on_started(self, result):
        self._set_enabled(True)
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
        self.status.setText(f"{len(entries)} self-test record(s).")

    def _on_error(self, err: str):
        self._set_enabled(True)
        self.status.setText("")
        QMessageBox.warning(self, "Self-test error", err)

    @staticmethod
    def _extract_entries(data: dict) -> list[dict]:
        """Normalise smartctl -l selftest -j into flat rows."""
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
