"""Tools panel — export report + AAM control.

Both operations go through the privileged helper and run on a worker thread so
the GUI never blocks. AAM (Automatic Acoustic Management) only applies to HDDs
that support it; the slider is disabled for SSD/NVMe.
"""
from __future__ import annotations

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from core.models import DiskInfo, DiskType
from core.service import DiskService


class _Worker(QThread):
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


class ToolsPanel(QWidget):
    def __init__(self, service: DiskService, parent=None):
        super().__init__(parent)
        self._service = service
        self._disk: DiskInfo | None = None
        self._worker: _Worker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(14)

        # Export report
        exp = QGroupBox("Export Report")
        ev = QHBoxLayout(exp)
        ev.addWidget(QLabel("Format:"))
        self.fmt = QComboBox()
        self.fmt.addItems(["txt", "html", "xml"])
        ev.addWidget(self.fmt)
        self.btn_export = QPushButton("Save Report")
        self.btn_export.clicked.connect(self._export)
        ev.addWidget(self.btn_export)
        ev.addStretch(1)
        root.addWidget(exp)

        # AAM control
        self.aam_box = QGroupBox("Acoustic Management (AAM) — HDD only")
        av = QVBoxLayout(self.aam_box)
        row = QHBoxLayout()
        row.addWidget(QLabel("Quiet"))
        self.aam = QSlider(Qt.Orientation.Horizontal)
        self.aam.setRange(128, 254)  # 0x80–0xFE
        self.aam.setValue(254)
        row.addWidget(self.aam, 1)
        row.addWidget(QLabel("Loud"))
        av.addLayout(row)
        self.btn_aam = QPushButton("Apply AAM")
        self.btn_aam.clicked.connect(self._apply_aam)
        av.addWidget(self.btn_aam)
        root.addWidget(self.aam_box)

        self.status = QLabel("")
        self.status.setStyleSheet("color:gray;")
        self.status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.status)
        root.addStretch(1)

        self.set_disk(None)

    def set_disk(self, disk: DiskInfo | None):
        self._disk = disk
        is_hdd = bool(disk and disk.disk_type == DiskType.HDD)
        self.aam_box.setEnabled(is_hdd)
        self.btn_export.setEnabled(True)

    # ------------------------------------------------------------- actions ----

    def _busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _export(self):
        if self._busy():
            return
        fmt = self.fmt.currentText()
        self.btn_export.setEnabled(False)
        self.status.setText("Generating report…")
        self._worker = _Worker(self._service.save_report, f"diskmaster.{fmt}", fmt)
        self._worker.done.connect(self._on_export)
        self._worker.failed.connect(self._on_error)
        self._worker.start()

    def _apply_aam(self):
        if not self._disk or self._busy():
            return
        level = self.aam.value()
        self.btn_aam.setEnabled(False)
        self.status.setText(f"Applying AAM level {level:#x}…")
        self._worker = _Worker(self._service.set_aam, self._disk.device, str(level))
        self._worker.done.connect(self._on_aam)
        self._worker.failed.connect(self._on_error)
        self._worker.start()

    # ------------------------------------------------------------- handlers ---

    def _on_export(self, path: str):
        self.btn_export.setEnabled(True)
        if path:
            self.status.setText(f"Report saved: {path}")
        else:
            self.status.setText("Report generated (path unknown).")

    def _on_aam(self, result: dict):
        self.btn_aam.setEnabled(True)
        rc = result.get("returncode") if isinstance(result, dict) else None
        self.status.setText(f"AAM applied (exit {rc}).")

    def _on_error(self, err: str):
        self.btn_export.setEnabled(True)
        self.btn_aam.setEnabled(True)
        self.status.setText("")
        QMessageBox.warning(self, "Tools error", err)


__all__ = ["ToolsPanel"]
