"""Information tab — disk identity fields plus the Tools actions.

Top: a key/value list (model, serial, firmware, capacity, …) like HDSentinel's
Information page. Bottom: the existing Tools widget (export report + AAM) folded
in, since this faithful layout has no separate Tools tab.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.models import DiskInfo
from core.service import DiskService
from .overview_panel import format_hours
from .tools_panel import ToolsPanel


class _Value(QLabel):
    def __init__(self):
        super().__init__("—")
        self.setStyleSheet("font-weight:bold;")
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)


class InformationPanel(QWidget):
    def __init__(self, service: DiskService, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        info = QGroupBox("Disk Information")
        form = QFormLayout(info)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(6)
        self.v_device = _Value()
        self.v_model = _Value()
        self.v_serial = _Value()
        self.v_wwn = _Value()
        self.v_firmware = _Value()
        self.v_type = _Value()
        self.v_size = _Value()
        self.v_power = _Value()
        self.v_health = _Value()
        self.v_written = _Value()
        self.v_read = _Value()
        form.addRow("Device:", self.v_device)
        form.addRow("Model:", self.v_model)
        form.addRow("Serial number:", self.v_serial)
        form.addRow("WWN:", self.v_wwn)
        form.addRow("Firmware:", self.v_firmware)
        form.addRow("Type:", self.v_type)
        form.addRow("Capacity:", self.v_size)
        form.addRow("Power on time:", self.v_power)
        form.addRow("Health / Performance:", self.v_health)
        form.addRow("Total host writes:", self.v_written)
        form.addRow("Total host reads:", self.v_read)
        root.addWidget(info)

        self.tools = ToolsPanel(service)
        root.addWidget(self.tools)
        root.addStretch(1)
        self.clear()

    def clear(self):
        for v in (self.v_device, self.v_model, self.v_serial, self.v_wwn,
                  self.v_firmware, self.v_type, self.v_size, self.v_power,
                  self.v_health, self.v_written, self.v_read):
            v.setText("—")
        self.tools.set_disk(None)

    def set_disk(self, disk: DiskInfo):
        self.v_device.setText(disk.device)
        self.v_model.setText(disk.model or "—")
        self.v_serial.setText(disk.serial or "—")
        self.v_wwn.setText(disk.wwn or "—")
        self.v_firmware.setText(disk.firmware or "—")
        self.v_type.setText(disk.disk_type.value)
        self.v_size.setText(disk.size_human)
        self.v_power.setText(format_hours(disk.power_on_hours))
        h = f"{disk.health}%" if disk.health >= 0 else "—"
        p = f"{disk.performance}%" if disk.performance >= 0 else "—"
        self.v_health.setText(f"{h} / {p}")
        self.v_written.setText(disk.total_written_human)
        self.v_read.setText(disk.total_read_human)
        self.tools.set_disk(disk)


__all__ = ["InformationPanel"]
