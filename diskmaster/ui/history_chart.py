"""History chart — temperature & health over time.

Drawn with QPainter directly so DiskMaster has **no charting dependency**
(PyQt6-Charts / pyqtgraph are not bundled — see plan §16 #9). Two series share
one widget: temperature (left axis, °C) and health (right axis, %). A range
selector picks the time window; data comes from :class:`core.db.HistoryDB`.
"""
from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.models import DiskHistory

_TEMP_COLOR = QColor("#ef6c00")
_HEALTH_COLOR = QColor("#2e7d32")
_GRID = QColor(128, 128, 128, 60)

# label -> seconds (None = all history)
_RANGES = [
    ("1 hour", 3600),
    ("24 hours", 86400),
    ("7 days", 604800),
    ("30 days", 2592000),
    ("All", None),
]


class _Plot(QWidget):
    """Pure paint surface for the two series."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._points: list[DiskHistory] = []
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_points(self, points: list[DiskHistory]):
        self._points = points
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        ml, mr, mt, mb = 44, 44, 12, 24  # margins for axes
        plot_w = max(1, w - ml - mr)
        plot_h = max(1, h - mt - mb)

        # Frame + horizontal gridlines (0–100 scale shared visually).
        p.setPen(QPen(_GRID, 1))
        for frac in (0, 0.25, 0.5, 0.75, 1.0):
            y = mt + plot_h * frac
            p.drawLine(ml, int(y), ml + plot_w, int(y))

        pts = self._points
        if len(pts) < 2:
            p.setPen(QColor(128, 128, 128))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Not enough history yet — keep DiskMaster running.")
            return

        t0 = pts[0].timestamp.timestamp()
        t1 = pts[-1].timestamp.timestamp()
        span = max(1.0, t1 - t0)

        temps = [d.temp for d in pts if d.temp >= 0]
        tmin = min(temps) - 2 if temps else 0
        tmax = max(temps) + 2 if temps else 60
        if tmax - tmin < 5:
            tmax = tmin + 5

        def x_of(ts: float) -> float:
            return ml + (ts - t0) / span * plot_w

        def y_temp(v: int) -> float:
            return mt + (1 - (v - tmin) / (tmax - tmin)) * plot_h

        def y_health(v: int) -> float:
            return mt + (1 - v / 100.0) * plot_h

        self._draw_series(p, pts, x_of, y_health, _HEALTH_COLOR,
                          lambda d: d.health)
        self._draw_series(p, pts, x_of, y_temp, _TEMP_COLOR, lambda d: d.temp)

        # Axis captions.
        p.setPen(_TEMP_COLOR)
        p.drawText(2, mt + 10, f"{tmax:.0f}°")
        p.drawText(2, mt + plot_h, f"{tmin:.0f}°")
        p.setPen(_HEALTH_COLOR)
        p.drawText(ml + plot_w + 4, mt + 10, "100%")
        p.drawText(ml + plot_w + 4, mt + plot_h, "0%")

    @staticmethod
    def _draw_series(p, pts, x_of, y_of, color, value):
        p.setPen(QPen(color, 2))
        prev = None
        for d in pts:
            v = value(d)
            if v < 0:
                prev = None
                continue
            cur = QPointF(x_of(d.timestamp.timestamp()), y_of(v))
            if prev is not None:
                p.drawLine(prev, cur)
            prev = cur


class HistoryChart(QWidget):
    """Range selector + plot + legend; tell it which disk to show."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db = db
        self._identity: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        top = QHBoxLayout()
        top.addWidget(QLabel("Range:"))
        self.range_box = QComboBox()
        for label, _secs in _RANGES:
            self.range_box.addItem(label)
        self.range_box.setCurrentIndex(1)  # 24 hours
        self.range_box.currentIndexChanged.connect(self.reload)
        top.addWidget(self.range_box)
        top.addStretch(1)
        top.addWidget(self._legend("Temperature", _TEMP_COLOR))
        top.addWidget(self._legend("Health", _HEALTH_COLOR))
        root.addLayout(top)

        self.plot = _Plot()
        root.addWidget(self.plot, 1)

    @staticmethod
    def _legend(text: str, color: QColor) -> QLabel:
        lbl = QLabel(f"⬤ {text}")
        lbl.setStyleSheet(f"color:{color.name()}; font-size:11px;")
        return lbl

    def set_identity(self, identity: str | None):
        self._identity = identity
        self.reload()

    def reload(self):
        if not self._identity or self._db is None:
            self.plot.set_points([])
            return
        _label, secs = _RANGES[self.range_box.currentIndex()]
        since = None
        if secs is not None:
            since = int(datetime.now().timestamp()) - secs
        self.plot.set_points(self._db.history(self._identity, since))


__all__ = ["HistoryChart"]
