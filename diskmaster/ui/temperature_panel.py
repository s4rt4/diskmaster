"""Temperature tab — current/max temperature and the temperature history."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.models import DiskInfo, DiskType
from .history_chart import HistoryChart
from .widgets import temp_color

_TYPE_WARN = {DiskType.HDD: 55, DiskType.SSD: 70, DiskType.NVME: 75}


class _Big(QFrame):
    def __init__(self, caption: str):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 10)
        cap = QLabel(caption)
        cap.setStyleSheet("color:gray; border:none;")
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value = QLabel("—")
        self.value.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value.setStyleSheet("font-size:34px; font-weight:bold; border:none;")
        lay.addWidget(cap)
        lay.addWidget(self.value)

    def set(self, text: str, color: str | None = None):
        self.value.setText(text)
        self.value.setStyleSheet(
            "font-size:34px; font-weight:bold; border:none;"
            + (f"color:{color};" if color else ""))


class TemperaturePanel(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.cur = _Big("Current Temperature")
        self.mx = _Big("Maximum (lifetime)")
        row.addWidget(self.cur)
        row.addWidget(self.mx)
        root.addLayout(row)

        cap = QLabel("Temperature history")
        cap.setStyleSheet("font-weight:bold;")
        root.addWidget(cap)
        self.chart = HistoryChart(db)
        root.addWidget(self.chart, 1)
        self.clear()

    def clear(self):
        self.cur.set("—")
        self.mx.set("—")
        self.chart.set_identity(None)

    def set_disk(self, disk: DiskInfo):
        warn = _TYPE_WARN.get(disk.disk_type, 55)
        if disk.temp_current >= 0:
            self.cur.set(f"{disk.temp_current} °C",
                         temp_color(disk.temp_current, warn).name())
        else:
            self.cur.set("—")
        self.mx.set(f"{disk.temp_max} °C" if disk.temp_max >= 0 else "—")
        self.chart.set_identity(disk.identity)


__all__ = ["TemperaturePanel"]
