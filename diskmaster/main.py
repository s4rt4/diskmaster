#!/usr/bin/env python3
"""DiskMaster — entry point.

Runs as a normal user. Privileged disk reads go through the helper (pkexec),
spawned on the first scan — see core/privhelper.py.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Allow `python main.py` from anywhere by putting the package root on the path.
_PKG_ROOT = Path(__file__).resolve().parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from PyQt6.QtGui import QIcon  # noqa: E402
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

from config.settings import Settings  # noqa: E402
from core.service import DiskService  # noqa: E402
from ui import theme  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402
from ui.tray_icon import TrayIcon  # noqa: E402

_ICON = _PKG_ROOT / "assets" / "icons" / "diskmaster.svg"


def _load_icon() -> QIcon:
    if _ICON.exists():
        icon = QIcon(str(_ICON))
        if not icon.isNull():
            return icon
    return QIcon.fromTheme("drive-harddisk")


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("DiskMaster")
    app.setApplicationDisplayName("DiskMaster")
    app.setDesktopFileName("diskmaster")

    icon = _load_icon()
    app.setWindowIcon(icon)

    settings = Settings()
    theme.apply_theme(app, settings.get("general", "theme", "light"))
    service = DiskService()
    window = MainWindow(service, settings, icon)

    tray = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = TrayIcon(window, icon)
        tray.show()
        # The window refreshes the tray tooltip on every poll (full + quick) and
        # uses the tray bubble as the notification fallback.
        window.set_tray(tray)
        # Don't quit when the window is closed if the tray is present.
        app.setQuitOnLastWindowClosed(False)

    start_min = settings.get("general", "start_minimized", False)
    if not (start_min and tray):
        window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
