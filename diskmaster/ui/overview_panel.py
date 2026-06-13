"""Overview tab — the HDSentinel landing page for a disk.

Performance + Health gradient bars with a qualitative word, a colour-coded status
box describing the disk, the key lifetime metrics, and a Health/Temperature chart
at the bottom.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.models import DiskInfo, Status
from .history_chart import HistoryChart
from .widgets import GradientBar, status_icon

_STATUS_BG = {
    Status.PERFECT: ("#dff3df", "#2e7d32"),
    Status.GOOD: ("#e3f2e3", "#388e3c"),
    Status.WARNING: ("#fff3e0", "#ef6c00"),
    Status.FAILURE: ("#fde0e0", "#c62828"),
    Status.UNKNOWN: ("#eceff1", "#546e7a"),
}
_STATUS_TEXT = {
    Status.PERFECT: ("The disk status is PERFECT. Problematic or weak sectors "
                     "were not found and there are no errors.", "No actions needed."),
    Status.GOOD: ("The disk status is GOOD. No errors that need attention were "
                  "found.", "No actions needed."),
    Status.WARNING: ("The disk status is WARNING. There may be weak sectors or "
                     "elevated error counters.",
                     "Back up important data and monitor the disk closely."),
    Status.FAILURE: ("The disk status is CRITICAL. Failures were detected.",
                     "Back up immediately and replace the drive."),
    Status.UNKNOWN: ("Disk health has not been read yet.",
                     "Click “Scan (admin)” to read health and SMART data."),
}


def _quality(pct: int) -> str:
    if pct < 0:
        return ""
    if pct >= 100:
        return "Perfect"
    if pct >= 90:
        return "Excellent"
    if pct >= 75:
        return "Good"
    if pct >= 50:
        return "Fair"
    if pct >= 25:
        return "Weak"
    return "Critical"


def format_hours(hours: int) -> str:
    if hours < 0:
        return "—"
    days, rem = divmod(hours, 24)
    if days:
        return f"{days:,} days, {rem} hours"
    return f"{rem} hours"


class _BarRow(QWidget):
    """icon + caption + gradient bar + qualitative word."""

    def __init__(self, caption: str):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.icon = QLabel()
        self.icon.setFixedWidth(18)
        cap = QLabel(caption)
        cap.setFixedWidth(96)
        cap.setStyleSheet("font-weight:bold;")
        self.bar = GradientBar(20)
        self.word = QLabel("")
        self.word.setFixedWidth(90)
        self.word.setStyleSheet("font-weight:bold;")
        lay.addWidget(self.icon)
        lay.addWidget(cap)
        lay.addWidget(self.bar, 1)
        lay.addWidget(self.word)

    def set(self, pct: int, status: Status):
        if pct >= 0:
            self.bar.setValue(pct)
        else:
            self.bar.setUnknown()
        self.word.setText(_quality(pct))
        self.icon.setPixmap(status_icon(status, 16).pixmap(16, 16))


class OverviewPanel(QWidget):
    repeat_test = pyqtSignal()

    def __init__(self, db, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(10)

        self.perf_row = _BarRow("Performance:")
        self.health_row = _BarRow("Health:")
        root.addWidget(self.perf_row)
        root.addWidget(self.health_row)

        self.status_box = QFrame()
        self.status_box.setFrameShape(QFrame.Shape.StyledPanel)
        sb = QVBoxLayout(self.status_box)
        sb.setContentsMargins(12, 10, 12, 10)
        self.status_desc = QLabel("")
        self.status_desc.setWordWrap(True)
        self.status_action = QLabel("")
        self.status_action.setStyleSheet("font-weight:bold;")
        self.status_action.setWordWrap(True)
        sb.addWidget(self.status_desc)
        sb.addWidget(self.status_action)
        root.addWidget(self.status_box)

        # Metrics + Repeat Test
        mrow = QHBoxLayout()
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(4)
        self.m_power = self._metric(grid, 0, "Power on time:")
        self.m_life = self._metric(grid, 1, "Estimated remaining lifetime:")
        self.m_temp = self._metric(grid, 2, "Current / Max temperature:")
        self.m_written = self._metric(grid, 3, "Total host writes:")
        self.m_read = self._metric(grid, 4, "Total host reads:")
        mrow.addLayout(grid, 1)
        self.btn_repeat = QPushButton("Repeat Test")
        self.btn_repeat.clicked.connect(self.repeat_test)
        mrow.addWidget(self.btn_repeat, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(mrow)

        chart_cap = QLabel("Health / Temperature")
        chart_cap.setStyleSheet("font-weight:bold;")
        root.addWidget(chart_cap)
        self.chart = HistoryChart(db)
        root.addWidget(self.chart, 1)

        self.clear()

    def _metric(self, grid: QGridLayout, row: int, caption: str) -> QLabel:
        cap = QLabel(caption)
        cap.setStyleSheet("color:gray;")
        val = QLabel("—")
        val.setStyleSheet("font-weight:bold;")
        val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(cap, row, 0, Qt.AlignmentFlag.AlignRight)
        grid.addWidget(val, row, 1)
        return val

    def clear(self):
        self.perf_row.set(-1, Status.UNKNOWN)
        self.health_row.set(-1, Status.UNKNOWN)
        self._set_status(Status.UNKNOWN)
        self.m_power.setText("—")
        self.m_life.setText("—")
        self.m_temp.setText("—")
        self.m_written.setText("—")
        self.m_read.setText("—")
        self.chart.set_identity(None)

    def _set_status(self, status: Status):
        bg, fg = _STATUS_BG.get(status, _STATUS_BG[Status.UNKNOWN])
        self.status_box.setStyleSheet(
            f"QFrame {{ background:{bg}; border:1px solid {fg}; border-radius:6px; }}"
            f"QLabel {{ color:{fg}; border:none; background:transparent; }}")
        desc, action = _STATUS_TEXT.get(status, _STATUS_TEXT[Status.UNKNOWN])
        self.status_desc.setText(desc)
        self.status_action.setText(action)

    def set_disk(self, disk: DiskInfo):
        self.perf_row.set(disk.performance, disk.status)
        self.health_row.set(disk.health, disk.status)
        self._set_status(disk.status)
        self.m_power.setText(format_hours(disk.power_on_hours))
        self.m_life.setText(disk.estimated_lifetime or "—")
        cur = f"{disk.temp_current} °C" if disk.temp_current >= 0 else "—"
        mx = f"{disk.temp_max} °C" if disk.temp_max >= 0 else "—"
        self.m_temp.setText(f"{cur}  /  {mx}")
        self.m_written.setText(disk.total_written_human)
        self.m_read.setText(disk.total_read_human)
        self.chart.set_identity(disk.identity)


__all__ = ["OverviewPanel", "format_hours"]
