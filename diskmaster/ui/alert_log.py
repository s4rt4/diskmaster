"""Alert-log panel — shows the alert history recorded in the DB.

Alerts are written by the main window whenever a threshold crosses (see
core.notifier). This tab is a read view over ``HistoryDB.recent_alerts`` plus a
button to acknowledge (clear) them. Refresh is cheap, so the window re-pulls
after every poll that produced new alerts.
"""
from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_COLS = ["Time", "Disk", "Type", "Message"]
_TYPE_COLOR = {
    "SMART_FAIL": QColor(198, 40, 40, 70),
    "TEMP_HIGH": QColor(239, 108, 0, 55),
    "HEALTH_LOW": QColor(239, 108, 0, 40),
}


class AlertLogPanel(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db = db

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        top = QHBoxLayout()
        self.heading = QLabel("Alert history")
        self.heading.setStyleSheet("font-weight:bold;")
        top.addWidget(self.heading)
        top.addStretch(1)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.reload)
        self.btn_clear = QPushButton("Acknowledge all")
        self.btn_clear.clicked.connect(self._acknowledge)
        top.addWidget(self.btn_refresh)
        top.addWidget(self.btn_clear)
        root.addLayout(top)

        self.table = QTableWidget(0, len(_COLS))
        self.table.setHorizontalHeaderLabels(_COLS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        self.reload()

    def reload(self):
        if self._db is None:
            return
        alerts = self._db.recent_alerts(200)
        self.table.setRowCount(0)
        for a in alerts:
            r = self.table.rowCount()
            self.table.insertRow(r)
            when = datetime.fromtimestamp(a["timestamp"]).strftime("%Y-%m-%d %H:%M")
            cells = [when, a["identity"], a["alert_type"] or "", a["message"] or ""]
            color = _TYPE_COLOR.get(a["alert_type"])
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if color:
                    item.setBackground(color)
                self.table.setItem(r, c, item)
        self.heading.setText(f"Alert history ({len(alerts)})")

    def _acknowledge(self):
        """Mark all alerts acknowledged. Kept as an audit trail in the DB, but
        cleared from this view."""
        if self._db is None:
            return
        self._db.acknowledge_all()
        self.reload()


__all__ = ["AlertLogPanel"]
