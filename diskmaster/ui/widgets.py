"""Custom-painted widgets that give DiskMaster its HDSentinel look.

* :class:`GradientBar` — the red→yellow→green health/performance bar, filled to a
  percentage with the value drawn on top.
* :class:`SolidBar` — a single-colour proportional bar used for temperature and
  free space (the magenta volume bars).
* :func:`status_icon` — the small green-check / amber-warn / red-fail badge shown
  beside each disk and on tabs.

All read their track/border colours from the active palette, so they follow the
light/dark theme automatically.
"""
from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QSizePolicy, QWidget

from core.models import Status

# Shared status colours.
_STATUS_COLOR = {
    Status.PERFECT: QColor(46, 125, 50),
    Status.GOOD: QColor(67, 160, 71),
    Status.WARNING: QColor(239, 153, 0),
    Status.FAILURE: QColor(198, 40, 40),
    Status.UNKNOWN: QColor(140, 145, 150),
}


def status_color(status: Status) -> QColor:
    return _STATUS_COLOR.get(status, _STATUS_COLOR[Status.UNKNOWN])


def status_icon(status: Status, size: int = 16) -> QIcon:
    """A round status badge with a glyph (✓ / ! / ✕)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = status_color(status)
    p.setBrush(QBrush(color))
    p.setPen(QPen(color.darker(120), 1))
    p.drawEllipse(1, 1, size - 2, size - 2)
    glyph = {
        Status.WARNING: "!",
        Status.FAILURE: "✕",
    }.get(status, "✓")
    p.setPen(QPen(QColor(255, 255, 255)))
    f = p.font()
    f.setPixelSize(int(size * 0.7))
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
    p.end()
    return QIcon(pm)


class _BarBase(QWidget):
    def __init__(self, height: int = 16, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setMinimumWidth(60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._text = ""

    def _track(self, p: QPainter, r: QRectF):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.palette().alternateBase())
        p.drawRoundedRect(r, 3, 3)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(self.palette().mid().color(), 1))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 3, 3)

    def _label(self, p: QPainter, r: QRectF, text: str):
        if not text:
            return
        p.setPen(QPen(self.palette().windowText().color()))
        f = p.font()
        f.setPixelSize(max(10, int(r.height() * 0.66)))
        f.setBold(True)
        p.setFont(f)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)


class GradientBar(_BarBase):
    """Red→yellow→green bar filled to ``value`` percent."""

    def __init__(self, height: int = 16, parent=None):
        super().__init__(height, parent)
        self._value = 0

    def setValue(self, v: int):
        self._value = max(0, min(100, int(v)))
        self._text = f"{self._value} %" if v >= 0 else "—"
        self.update()

    def setUnknown(self):
        self._value = 0
        self._text = "—"
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0, 0, self.width(), self.height())
        self._track(p, r)
        if self._value > 0:
            grad = QLinearGradient(0, 0, self.width(), 0)
            grad.setColorAt(0.0, QColor(206, 51, 51))
            grad.setColorAt(0.5, QColor(230, 193, 0))
            grad.setColorAt(1.0, QColor(58, 160, 58))
            fill_w = self.width() * self._value / 100.0
            p.setClipRect(QRectF(0, 0, fill_w, self.height()))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawRoundedRect(r, 3, 3)
            p.setClipping(False)
        self._label(p, r, self._text)


class SolidBar(_BarBase):
    """Single-colour bar filled to ``fraction`` (0..1) with arbitrary text."""

    def __init__(self, color: QColor, height: int = 16, parent=None):
        super().__init__(height, parent)
        self._color = color
        self._fraction = 0.0

    def set(self, fraction: float, text: str, color: QColor | None = None):
        self._fraction = max(0.0, min(1.0, fraction))
        self._text = text
        if color is not None:
            self._color = color
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0, 0, self.width(), self.height())
        self._track(p, r)
        if self._fraction > 0:
            fill_w = self.width() * self._fraction
            p.setClipRect(QRectF(0, 0, fill_w, self.height()))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(self._color))
            p.drawRoundedRect(r, 3, 3)
            p.setClipping(False)
        self._label(p, r, self._text)


def temp_color(temp: int, warn: int = 50) -> QColor:
    """Green (cool) → yellow → orange → red (hot), pivoting on the warn point."""
    if temp < 0:
        return QColor(140, 145, 150)
    if temp >= warn + 10:
        return QColor(198, 40, 40)
    if temp >= warn:
        return QColor(239, 108, 0)
    if temp >= warn - 12:
        return QColor(214, 183, 0)
    return QColor(67, 160, 71)


__all__ = ["GradientBar", "SolidBar", "status_icon", "status_color",
           "temp_color"]
