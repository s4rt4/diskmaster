"""Disk Performance tab — live I/O throughput from sysfs (no root).

Samples ``/sys/block/<dev>/stat`` once a second via its own IOSampler (kept
independent of the poller's sampler so the two don't disturb each other's
deltas) and shows read/write throughput and busy-time utilisation. Read/write
bars auto-scale to the largest rate seen so far.
"""
from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QFormLayout, QGroupBox, QLabel, QVBoxLayout, QWidget

from core.backends.sysfs import IOSampler
from core.models import DiskInfo
from .widgets import SolidBar

_READ = QColor(33, 118, 190)
_WRITE = QColor(216, 120, 0)
_UTIL = QColor(120, 144, 156)


class PerformancePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._sampler = IOSampler()
        self._name: str | None = None
        self._max_read = 1.0
        self._max_write = 1.0

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        box = QGroupBox("Live I/O")
        form = QFormLayout(box)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        self.read_bar = SolidBar(_READ, 20)
        self.write_bar = SolidBar(_WRITE, 20)
        self.util_bar = SolidBar(_UTIL, 20)
        form.addRow("Read:", self.read_bar)
        form.addRow("Write:", self.write_bar)
        form.addRow("Utilisation:", self.util_bar)
        root.addWidget(box)

        self.note = QLabel("Select a disk to see live throughput. "
                           "Counters come from sysfs — no admin needed.")
        self.note.setStyleSheet("color:gray;")
        self.note.setWordWrap(True)
        root.addWidget(self.note)
        root.addStretch(1)

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

    def set_disk(self, disk: DiskInfo | None):
        self._name = disk.device.rsplit("/", 1)[-1] if disk else None
        self._max_read = self._max_write = 1.0
        if self._name:
            self._sampler.reset(self._name)
            self._sampler.sample(self._name)  # prime baseline
            self._reset_bars()
            self._timer.start()
        else:
            self._timer.stop()
            self._reset_bars()

    def _reset_bars(self):
        self.read_bar.set(0.0, "—")
        self.write_bar.set(0.0, "—")
        self.util_bar.set(0.0, "—")

    def _tick(self):
        if not self._name:
            return
        st = self._sampler.sample(self._name)
        if st is None:
            return
        self._max_read = max(self._max_read, st.read_mbps)
        self._max_write = max(self._max_write, st.write_mbps)
        self.read_bar.set(st.read_mbps / self._max_read,
                          f"{st.read_mbps:.1f} MB/s")
        self.write_bar.set(st.write_mbps / self._max_write,
                           f"{st.write_mbps:.1f} MB/s")
        self.util_bar.set(st.utilization_pct / 100.0,
                          f"{st.utilization_pct:.0f} %")

    def hideEvent(self, _e):
        self._timer.stop()

    def showEvent(self, _e):
        if self._name:
            self._timer.start()


__all__ = ["PerformancePanel"]
