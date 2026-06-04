"""Settings dialog — edits the TOML-backed config.Settings.

Flat form over the same sections as config.settings.DEFAULTS. On accept it writes
each field back, saves to disk, and returns; the caller applies live changes
(e.g. poll interval) from the updated Settings object.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from config.settings import Settings


def _spin(lo: int, hi: int, val: int, suffix: str = "") -> QSpinBox:
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(int(val))
    if suffix:
        s.setSuffix(suffix)
    return s


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("DiskMaster Settings")
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        g = settings.get

        # General
        gen = QGroupBox("General")
        gf = QFormLayout(gen)
        self.theme = QComboBox()
        self.theme.addItems(["system", "dark", "light"])
        self.theme.setCurrentText(g("general", "theme", "system"))
        self.start_min = QCheckBox()
        self.start_min.setChecked(bool(g("general", "start_minimized", False)))
        gf.addRow("Theme:", self.theme)
        gf.addRow("Start minimized to tray:", self.start_min)
        root.addWidget(gen)

        # Polling
        pol = QGroupBox("Polling")
        pf = QFormLayout(pol)
        self.quick = _spin(5, 3600, g("polling", "quick_interval_sec", 30), " s")
        self.full = _spin(30, 86400, g("polling", "full_interval_sec", 300), " s")
        self.skip_standby = QCheckBox()
        self.skip_standby.setChecked(bool(g("polling", "skip_standby", True)))
        pf.addRow("Quick interval:", self.quick)
        pf.addRow("Full interval:", self.full)
        pf.addRow("Skip standby disks:", self.skip_standby)
        root.addWidget(pol)

        # Thresholds
        thr = QGroupBox("Thresholds")
        tf = QFormLayout(thr)
        self.t_hdd = _spin(20, 100, g("thresholds", "temp_hdd", 55), " °C")
        self.t_ssd = _spin(20, 100, g("thresholds", "temp_ssd", 70), " °C")
        self.t_nvme = _spin(20, 120, g("thresholds", "temp_nvme", 75), " °C")
        self.h_min = _spin(0, 100, g("thresholds", "health_min", 80), " %")
        tf.addRow("HDD temp warning:", self.t_hdd)
        tf.addRow("SSD temp warning:", self.t_ssd)
        tf.addRow("NVMe temp warning:", self.t_nvme)
        tf.addRow("Health warning below:", self.h_min)
        root.addWidget(thr)

        # Paths + retention
        misc = QGroupBox("Paths & History")
        mf = QFormLayout(misc)
        self.p_hds = QLineEdit(g("paths", "hdsentinel", ""))
        self.p_hds.setPlaceholderText("auto-detect")
        self.p_smart = QLineEdit(g("paths", "smartctl", ""))
        self.p_smart.setPlaceholderText("auto-detect")
        self.retention = _spin(0, 3650, g("history", "retention_days", 90), " days")
        mf.addRow("HDSentinel path:", self.p_hds)
        mf.addRow("smartctl path:", self.p_smart)
        mf.addRow("History retention:", self.retention)
        root.addWidget(misc)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _accept(self):
        s = self._settings
        s.set("general", "theme", self.theme.currentText())
        s.set("general", "start_minimized", self.start_min.isChecked())
        s.set("polling", "quick_interval_sec", self.quick.value())
        s.set("polling", "full_interval_sec", self.full.value())
        s.set("polling", "skip_standby", self.skip_standby.isChecked())
        s.set("thresholds", "temp_hdd", self.t_hdd.value())
        s.set("thresholds", "temp_ssd", self.t_ssd.value())
        s.set("thresholds", "temp_nvme", self.t_nvme.value())
        s.set("thresholds", "health_min", self.h_min.value())
        s.set("paths", "hdsentinel", self.p_hds.text().strip())
        s.set("paths", "smartctl", self.p_smart.text().strip())
        s.set("history", "retention_days", self.retention.value())
        s.save()
        self.accept()


__all__ = ["SettingsDialog"]
