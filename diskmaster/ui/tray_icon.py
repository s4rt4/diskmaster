"""System tray icon with quick actions and per-disk tooltip."""
from __future__ import annotations

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from core.models import DiskInfo


class TrayIcon(QSystemTrayIcon):
    def __init__(self, window, icon: QIcon, parent=None):
        super().__init__(icon, parent)
        self._window = window
        self.setToolTip("DiskMaster")

        menu = QMenu()
        act_show = menu.addAction("Show / Hide")
        act_show.triggered.connect(self._toggle)
        act_scan = menu.addAction("Scan now")
        act_scan.triggered.connect(window._start_scan)
        menu.addSeparator()
        act_quit = menu.addAction("Quit")
        act_quit.triggered.connect(QApplication.instance().quit)
        self.setContextMenu(menu)

        self.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._toggle()

    def _toggle(self):
        if self._window.isVisible():
            self._window.hide()
        else:
            self._window.showNormal()
            self._window.raise_()
            self._window.activateWindow()

    def update_disks(self, disks: list[DiskInfo]):
        lines = ["DiskMaster"]
        for d in disks:
            temp = f"{d.temp_current}°C" if d.temp_current >= 0 else "?"
            health = f"{d.health}%" if d.health >= 0 else "?"
            lines.append(f"{d.device}: {temp}, health {health}")
        self.setToolTip("\n".join(lines))
