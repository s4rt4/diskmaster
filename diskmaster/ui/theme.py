"""Theme handling — light (HDSentinel-like) and dark palettes.

We force the **Fusion** style so the palette swap works identically across KDE /
GNOME / XFCE and X11 / Wayland (the native styles ignore a custom palette). The
light theme mimics HDSentinel's clean blue-grey chrome; the dark theme is a
comfortable low-contrast counterpart. Custom-painted widgets read their track /
border colours from the active palette, so they follow the theme automatically.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette

# Modes in toggle order.
MODES = ("light", "dark")

# Accent used for selections / headers (HDSentinel-ish blue).
ACCENT = QColor(53, 120, 190)


def _light_palette() -> QPalette:
    p = QPalette()
    window = QColor(240, 243, 246)
    base = QColor(255, 255, 255)
    text = QColor(28, 32, 36)
    p.setColor(QPalette.ColorRole.Window, window)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(244, 247, 250))
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, window)
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 225))
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Highlight, ACCENT)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Mid, QColor(190, 198, 206))
    p.setColor(QPalette.ColorRole.Link, ACCENT)
    return p


def _dark_palette() -> QPalette:
    p = QPalette()
    window = QColor(38, 41, 45)
    base = QColor(28, 30, 33)
    text = QColor(222, 226, 230)
    p.setColor(QPalette.ColorRole.Window, window)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(44, 47, 51))
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, QColor(52, 56, 61))
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(52, 56, 61))
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Highlight, ACCENT)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Mid, QColor(70, 75, 80))
    p.setColor(QPalette.ColorRole.Link, QColor(110, 170, 230))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(120, 124, 128))
    return p


_QSS = """
QGroupBox {
    border: 1px solid palette(mid);
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 6px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QTabWidget::pane {
    border: 1px solid palette(mid);
    border-radius: 4px;
    top: -1px;
}
QTabBar { qproperty-drawBase: 0; }
QTabBar::tab {
    background: transparent;
    border: 1px solid transparent;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 6px 14px;
    margin-right: 1px;
    margin-bottom: 1px;
}
QTabBar::tab:hover:!selected {
    background: rgba(128, 128, 128, 0.12);
}
QTabBar::tab:selected {
    background: palette(base);
    border: 1px solid palette(mid);
    border-bottom: 2px solid %ACCENT%;
    font-weight: bold;
}
QTableWidget { gridline-color: palette(mid); }
""".replace("%ACCENT%", ACCENT.name())


def normalize(mode: str) -> str:
    mode = (mode or "").lower()
    if mode in MODES:
        return mode
    return "light"  # 'system' and anything unknown default to the familiar light


def apply_theme(app, mode: str) -> str:
    """Apply ``mode`` ('light'/'dark', else light). Returns the applied mode."""
    mode = normalize(mode)
    app.setStyle("Fusion")
    app.setPalette(_light_palette() if mode == "light" else _dark_palette())
    app.setStyleSheet(_QSS)
    return mode


def next_mode(mode: str) -> str:
    """Toggle light <-> dark."""
    return "dark" if normalize(mode) == "light" else "light"


__all__ = ["apply_theme", "next_mode", "normalize", "MODES", "ACCENT"]
