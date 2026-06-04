"""SMART attributes table widget."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
)

from core.models import SmartAttribute

_COLS = ["ID", "Attribute", "Value", "Worst", "Threshold", "Raw", "Status"]
_ROW_COLOR = {
    "FAILED": QColor(198, 40, 40, 60),
    "WARNING": QColor(239, 108, 0, 50),
}


class SmartTable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(0, len(_COLS), parent)
        self.setHorizontalHeaderLabels(_COLS)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        hdr = self.horizontalHeader()
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c in (0, 2, 3, 4, 5, 6):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

    def set_attributes(self, attrs: list[SmartAttribute]):
        self.setRowCount(0)
        for a in attrs:
            r = self.rowCount()
            self.insertRow(r)
            cells = [
                str(a.attr_id), a.name, str(a.value), str(a.worst),
                str(a.threshold), str(a.raw_value), a.status,
            ]
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c in (0, 2, 3, 4, 5):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                color = _ROW_COLOR.get(a.status)
                if color:
                    item.setBackground(color)
                self.setItem(r, c, item)
