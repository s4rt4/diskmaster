"""Left-column disk cards + volume cards — the HDSentinel device list.

:class:`DiskCard` shows one physical disk: status badge, model + capacity,
"Disk: N", a health gradient bar and a temperature bar. :class:`DiskListPanel`
stacks the cards and tracks selection. :class:`VolumePanel` shows mounted
volumes with a magenta free-space bar (the C:/D: section).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from core.models import DiskInfo, DiskType, VolumeInfo
from .theme import ACCENT
from .widgets import GradientBar, SolidBar, status_icon, temp_color

_TYPE_WARN = {DiskType.HDD: 55, DiskType.SSD: 70, DiskType.NVME: 75}
_FREE_COLOR = QColor(205, 60, 160)   # HDSentinel magenta


class DiskCard(QFrame):
    clicked = pyqtSignal(str)   # device

    def __init__(self, disk: DiskInfo, index: int, parent=None):
        super().__init__(parent)
        self.device = disk.device
        self._index = index
        self._selected = False
        self.setObjectName("DiskCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(3)

        head = QHBoxLayout()
        head.setSpacing(6)
        self.icon = QLabel()
        self.icon.setFixedWidth(18)
        self.title = QLabel()
        self.title.setStyleSheet("font-weight:bold;")
        self.title.setWordWrap(False)
        self.diskno = QLabel(f"Disk: {index}")
        self.diskno.setStyleSheet("color:gray; font-size:11px;")
        head.addWidget(self.icon)
        head.addWidget(self.title, 1)
        head.addWidget(self.diskno)
        lay.addLayout(head)

        grid = QGridLayout()
        grid.setContentsMargins(20, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(3)
        cap_h = QLabel("Health:")
        cap_h.setStyleSheet("color:gray; font-size:11px;")
        cap_t = QLabel("Temp.:")
        cap_t.setStyleSheet("color:gray; font-size:11px;")
        self.health_bar = GradientBar(15)
        self.temp_bar = SolidBar(QColor(120, 120, 120), 15)
        self.temp_bar.setMaximumWidth(120)
        grid.addWidget(cap_h, 0, 0)
        grid.addWidget(self.health_bar, 0, 1)
        grid.addWidget(cap_t, 1, 0)
        grid.addWidget(self.temp_bar, 1, 1, Qt.AlignmentFlag.AlignLeft)
        lay.addLayout(grid)

        self.update_disk(disk)
        self.set_selected(False)

    def update_disk(self, disk: DiskInfo):
        self.icon.setPixmap(status_icon(disk.status, 16).pixmap(16, 16))
        size = disk.size_human
        self.title.setText(f"{disk.model or disk.disk_type.value}  ({size})")
        self.title.setToolTip(f"{disk.device} — {disk.model}")
        if disk.health >= 0:
            self.health_bar.setValue(disk.health)
        else:
            self.health_bar.setUnknown()
        warn = _TYPE_WARN.get(disk.disk_type, 55)
        if disk.temp_current >= 0:
            frac = min(disk.temp_current / 70.0, 1.0)
            self.temp_bar.set(frac, f"{disk.temp_current} °C",
                              temp_color(disk.temp_current, warn))
        else:
            self.temp_bar.set(0.0, "—")

    def set_selected(self, on: bool):
        self._selected = on
        if on:
            self.setStyleSheet(
                "#DiskCard { background: rgba(%d,%d,%d,40); "
                "border:1px solid %s; border-radius:6px; }"
                % (ACCENT.red(), ACCENT.green(), ACCENT.blue(), ACCENT.name()))
        else:
            self.setStyleSheet(
                "#DiskCard { border:1px solid palette(mid); border-radius:6px; }")

    def mousePressEvent(self, _e):
        self.clicked.emit(self.device)


class DiskListPanel(QWidget):
    selected = pyqtSignal(str)   # device

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(6, 6, 6, 6)
        self._lay.setSpacing(6)
        self._cards: dict[str, DiskCard] = {}
        self._current: str | None = None
        self._lay.addStretch(1)

    def set_disks(self, disks: list[DiskInfo]):
        prev = self._current
        # Clear existing cards (keep the trailing stretch).
        for card in self._cards.values():
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()

        for i, disk in enumerate(disks):
            card = DiskCard(disk, i)
            card.clicked.connect(self._on_click)
            self._lay.insertWidget(self._lay.count() - 1, card)
            self._cards[disk.device] = card

        if disks:
            target = prev if prev in self._cards else disks[0].device
            self.select(target)

    def update_disk(self, disk: DiskInfo):
        card = self._cards.get(disk.device)
        if card:
            card.update_disk(disk)

    def select(self, device: str):
        if device not in self._cards:
            return
        self._current = device
        for dev, card in self._cards.items():
            card.set_selected(dev == device)
        self.selected.emit(device)

    def _on_click(self, device: str):
        self.select(device)

    @property
    def current(self) -> str | None:
        return self._current

    def disk_index(self) -> dict[str, int]:
        """device-name (sda) -> card index, for the volumes' 'Disk: N'."""
        out = {}
        for i, dev in enumerate(self._cards):
            out[dev.rsplit("/", 1)[-1]] = i
        return out


class _VolumeCard(QFrame):
    def __init__(self, vol: VolumeInfo, disk_no: int | None, parent=None):
        super().__init__(parent)
        self.setObjectName("VolCard")
        self.setStyleSheet(
            "#VolCard { border:1px solid palette(mid); border-radius:6px; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 5, 8, 5)
        lay.setSpacing(3)

        head = QHBoxLayout()
        title = QLabel(f"{vol.label}  ({vol.total_human})")
        title.setStyleSheet("font-weight:bold;")
        head.addWidget(title, 1)
        if disk_no is not None:
            no = QLabel(f"Disk: {disk_no}")
            no.setStyleSheet("color:gray; font-size:11px;")
            head.addWidget(no)
        lay.addLayout(head)

        row = QHBoxLayout()
        cap = QLabel("Used Space:")
        cap.setStyleSheet("color:gray; font-size:11px;")
        cap.setFixedWidth(72)
        bar = SolidBar(_FREE_COLOR, 15)
        # Colour the *used* portion; the empty track is the free space left.
        bar.set(vol.used_fraction, f"{vol.used_human} used")
        row.addWidget(cap)
        row.addWidget(bar, 1)
        lay.addLayout(row)


class VolumePanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(6, 0, 6, 6)
        self._lay.setSpacing(6)
        self._cards: list[_VolumeCard] = []
        header = QLabel("Volumes")
        header.setStyleSheet("font-weight:bold; padding:2px;")
        self._lay.addWidget(header)
        self._lay.addStretch(1)

    def set_volumes(self, volumes: list[VolumeInfo], disk_index: dict[str, int]):
        for c in self._cards:
            c.setParent(None)
            c.deleteLater()
        self._cards.clear()
        for vol in volumes:
            no = disk_index.get(vol.parent)
            card = _VolumeCard(vol, no)
            self._lay.insertWidget(self._lay.count() - 1, card)
            self._cards.append(card)


__all__ = ["DiskCard", "DiskListPanel", "VolumePanel"]
