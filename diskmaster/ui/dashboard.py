"""DashboardPanel — overview of a single disk (health, temp, status, lifetime)."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.models import DiskInfo, Status

_STATUS_COLOR = {
    Status.PERFECT: "#2e7d32",
    Status.GOOD: "#388e3c",
    Status.WARNING: "#ef6c00",
    Status.FAILURE: "#c62828",
    Status.UNKNOWN: "#616161",
}


def _badge(text: str, color: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"background:{color}; color:white; padding:3px 10px;"
        "border-radius:8px; font-weight:bold;"
    )
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
    return lbl


class _Metric(QFrame):
    """A small card: caption on top, big value below."""

    def __init__(self, caption: str):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame { border:1px solid rgba(128,128,128,0.3); border-radius:8px; }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        cap = QLabel(caption)
        cap.setStyleSheet("color: gray; font-size: 11px; border:none;")
        self.value = QLabel("—")
        self.value.setStyleSheet("font-size: 20px; font-weight: bold; border:none;")
        lay.addWidget(cap)
        lay.addWidget(self.value)

    def set(self, text: str):
        self.value.setText(text)


class DashboardPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        # Header: model / device / badges
        header = QHBoxLayout()
        self.title = QLabel("No disk selected")
        self.title.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.type_badge = _badge("", "#455a64")
        self.status_badge = _badge("", "#616161")
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.type_badge)
        header.addWidget(self.status_badge)
        root.addLayout(header)

        self.subtitle = QLabel("")
        self.subtitle.setStyleSheet("color: gray;")
        root.addWidget(self.subtitle)

        # Health bar
        health_row = QVBoxLayout()
        self.health_caption = QLabel("Health")
        self.health_caption.setStyleSheet("color: gray; font-size: 11px;")
        self.health_bar = QProgressBar()
        self.health_bar.setRange(0, 100)
        self.health_bar.setTextVisible(True)
        self.health_bar.setFixedHeight(22)
        health_row.addWidget(self.health_caption)
        health_row.addWidget(self.health_bar)
        root.addLayout(health_row)

        # Metric grid
        grid = QGridLayout()
        grid.setSpacing(10)
        self.m_temp = _Metric("Temperature")
        self.m_temp_max = _Metric("Max Temp")
        self.m_perf = _Metric("Performance")
        self.m_poh = _Metric("Power-on Hours")
        self.m_life = _Metric("Est. Lifetime")
        self.m_size = _Metric("Capacity")
        grid.addWidget(self.m_temp, 0, 0)
        grid.addWidget(self.m_temp_max, 0, 1)
        grid.addWidget(self.m_perf, 0, 2)
        grid.addWidget(self.m_poh, 1, 0)
        grid.addWidget(self.m_life, 1, 1)
        grid.addWidget(self.m_size, 1, 2)
        root.addLayout(grid)

        # Identity footer
        self.identity = QLabel("")
        self.identity.setStyleSheet("color: gray; font-size: 11px;")
        self.identity.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        root.addWidget(self.identity)
        root.addStretch(1)

        self.clear()

    def clear(self):
        self.title.setText("No disk selected")
        self.subtitle.setText("")
        self.type_badge.hide()
        self.status_badge.hide()
        self.health_bar.setValue(0)
        self.health_bar.setFormat("—")
        for m in (self.m_temp, self.m_temp_max, self.m_perf,
                  self.m_poh, self.m_life, self.m_size):
            m.set("—")
        self.identity.setText("")

    def set_disk(self, disk: DiskInfo):
        self.title.setText(disk.model or disk.device)
        self.subtitle.setText(disk.device)

        self.type_badge.setText(disk.disk_type.value)
        self.type_badge.show()
        self.status_badge.setText(disk.status.value)
        self.status_badge.setStyleSheet(
            f"background:{_STATUS_COLOR.get(disk.status, '#616161')}; color:white;"
            "padding:3px 10px; border-radius:8px; font-weight:bold;"
        )
        self.status_badge.show()

        if disk.health >= 0:
            self.health_bar.setValue(disk.health)
            self.health_bar.setFormat(f"{disk.health}%")
            color = ("#2e7d32" if disk.health >= 80
                     else "#ef6c00" if disk.health >= 50 else "#c62828")
            self.health_bar.setStyleSheet(
                f"QProgressBar::chunk {{ background:{color}; border-radius:4px; }}"
                "QProgressBar { border:1px solid rgba(128,128,128,0.4);"
                "border-radius:5px; text-align:center; }"
            )
        else:
            self.health_bar.setValue(0)
            self.health_bar.setFormat("unknown")

        self.m_temp.set(f"{disk.temp_current}°C" if disk.temp_current >= 0 else "—")
        self.m_temp_max.set(f"{disk.temp_max}°C" if disk.temp_max >= 0 else "—")
        self.m_perf.set(f"{disk.performance}%" if disk.performance >= 0 else "—")
        self.m_poh.set(f"{disk.power_on_hours:,} h" if disk.power_on_hours >= 0 else "—")
        self.m_life.set(disk.estimated_lifetime or "—")
        self.m_size.set(disk.size_human)

        sn = disk.serial or "(none)"
        self.identity.setText(
            f"Serial: {sn}    Firmware: {disk.firmware or '—'}"
        )
