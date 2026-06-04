"""Main application window — HDSentinel-style layout.

Left column: physical-disk cards (top) and mounted-volume cards (bottom).
Right: seven tabs mirroring HDSentinel — Overview, Temperature, S.M.A.R.T.,
Information, Log, Disk Performance, Alerts. A toolbar offers Scan, a light/dark
theme toggle, Settings and About; the status bar shows when data was last read.
"""
from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QSystemTrayIcon,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from config.settings import Settings
from core.db import HistoryDB
from core.models import DiskInfo
from core.notifier import Notifier
from core.poller import PollerWorker
from core.service import DiskService
from core.privclient import PrivError

from . import theme
from .alert_log import AlertLogPanel
from .disk_card import DiskListPanel, VolumePanel
from .information_panel import InformationPanel
from .overview_panel import OverviewPanel
from .performance_panel import PerformancePanel
from .selftest_panel import SelfTestPanel
from .settings_dialog import SettingsDialog
from .smart_table import SmartTable
from .temperature_panel import TemperaturePanel
from .widgets import status_icon


class _SmartLoader(QThread):
    """One-shot SMART fetch off the GUI thread."""
    loaded = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)

    def __init__(self, service: DiskService, device: str, parent=None):
        super().__init__(parent)
        self._service = service
        self._device = device

    def run(self):
        try:
            attrs, _raw = self._service.load_smart(self._device)
            self.loaded.emit(self._device, attrs)
        except (PrivError, Exception) as e:  # noqa: BLE001
            self.failed.emit(self._device, str(e))


class MainWindow(QMainWindow):
    def __init__(self, service: DiskService, settings: Settings, icon: QIcon | None = None):
        super().__init__()
        self.service = service
        self.settings = settings
        self.db = HistoryDB()
        self.db.cleanup(int(settings.get("history", "retention_days", 90)))
        self.notifier = Notifier(settings)
        self._tray = None
        self._disks: dict[str, DiskInfo] = {}
        self._smart_loader: _SmartLoader | None = None
        self._theme = theme.normalize(settings.get("general", "theme", "light"))

        self.setWindowTitle("DiskMaster")
        if icon:
            self.setWindowIcon(icon)
        self.resize(1000, 660)

        self._build_toolbar()
        self._build_central()
        self._build_statusbar()

        full = self.settings.get("polling", "full_interval_sec", 300)
        quick = self.settings.get("polling", "quick_interval_sec", 30)
        self.poller = PollerWorker(self.service, full, quick)
        self.poller.disks_updated.connect(self._on_disks_updated)
        self.poller.quick_updated.connect(self._on_quick_updated)
        self.poller.error.connect(self._on_poll_error)
        self.poller.status.connect(self._set_status)

        self._populate(self.service.sysfs_disks())
        self._refresh_volumes()
        self._set_status("Ready — click “Scan” to read health (requires admin).")

    # ----------------------------------------------------------- UI building --

    def _build_toolbar(self):
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        self.act_scan = QAction("⟳  Scan (admin)", self)
        self.act_scan.triggered.connect(self._start_scan)
        tb.addAction(self.act_scan)
        tb.addSeparator()
        self.act_theme = QAction("", self)
        self.act_theme.triggered.connect(self._toggle_theme)
        tb.addAction(self.act_theme)
        self._sync_theme_action()
        act_settings = QAction("Settings", self)
        act_settings.triggered.connect(self._open_settings)
        tb.addAction(act_settings)
        act_about = QAction("About", self)
        act_about.triggered.connect(self._about)
        tb.addAction(act_about)

    def _build_central(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left column: disks (top) + volumes (bottom), each scrollable.
        left = QSplitter(Qt.Orientation.Vertical)
        self.disk_panel = DiskListPanel()
        self.disk_panel.selected.connect(self._on_select_device)
        self.volume_panel = VolumePanel()
        left.addWidget(self._scroll(self.disk_panel))
        left.addWidget(self._scroll(self.volume_panel))
        left.setStretchFactor(0, 3)
        left.setStretchFactor(1, 1)

        # Right: the seven HDSentinel tabs.
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.overview = OverviewPanel(self.db)
        self.overview.repeat_test.connect(self._start_scan)
        self.temperature = TemperaturePanel(self.db)
        self.smart_tab = self._build_smart_tab()
        self.information = InformationPanel(self.service)
        self.log_panel = SelfTestPanel(self.service)
        self.performance = PerformancePanel()
        self.alert_log = AlertLogPanel(self.db)

        self.tabs.addTab(self.overview, "Overview")
        self.tabs.addTab(self.temperature, "Temperature")
        self.tabs.addTab(self.smart_tab, "S.M.A.R.T.")
        self.tabs.addTab(self.information, "Information")
        self.tabs.addTab(self.log_panel, "Log")
        self.tabs.addTab(self.performance, "Disk Performance")
        self.tabs.addTab(self.alert_log, "Alerts")

        splitter.addWidget(left)
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 700])
        self.setCentralWidget(splitter)

    @staticmethod
    def _scroll(widget: QWidget) -> QScrollArea:
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sc.setFrameShape(QScrollArea.Shape.NoFrame)
        sc.setWidget(widget)
        return sc

    def _build_smart_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        self.btn_load_smart = QPushButton("Load SMART data")
        self.btn_load_smart.clicked.connect(self._load_smart)
        self.smart_table = SmartTable()
        v.addWidget(self.btn_load_smart)
        v.addWidget(self.smart_table)
        return w

    def _build_statusbar(self):
        self.status_label = QLabel("")
        self.statusBar().addWidget(self.status_label)
        self.priv_label = QLabel("")
        self.statusBar().addPermanentWidget(self.priv_label)

    # --------------------------------------------------------------- theme ----

    def _sync_theme_action(self):
        nxt = "Dark" if self._theme == "light" else "Light"
        glyph = "☾" if self._theme == "light" else "☀"
        self.act_theme.setText(f"{glyph}  {nxt} mode")
        self.act_theme.setToolTip(f"Switch to {nxt.lower()} theme")

    def _toggle_theme(self):
        self._theme = theme.next_mode(self._theme)
        theme.apply_theme(QApplication.instance(), self._theme)
        self.settings.set("general", "theme", self._theme)
        self.settings.save()
        self._sync_theme_action()
        # Re-apply selection styling so cards pick up the new palette.
        if self.disk_panel.current:
            self.disk_panel.select(self.disk_panel.current)

    # --------------------------------------------------------------- tray ----

    def set_tray(self, tray):
        self._tray = tray
        self.notifier.set_tray_callback(
            lambda title, msg: tray.showMessage(
                title, msg, QSystemTrayIcon.MessageIcon.Warning, 8000))

    def _refresh_tray(self):
        if self._tray:
            self._tray.update_disks(list(self._disks.values()))

    # --------------------------------------------------------------- actions --

    def _start_scan(self):
        if not self.poller.isRunning():
            self.poller.start()
        else:
            self.poller.refresh_now()
        self._set_status("Scanning… (an admin prompt may appear)")

    def _load_smart(self):
        device = self.disk_panel.current
        if not device:
            return
        self.btn_load_smart.setEnabled(False)
        self.btn_load_smart.setText("Loading…")
        self._smart_loader = _SmartLoader(self.service, device)
        self._smart_loader.loaded.connect(self._on_smart_loaded)
        self._smart_loader.failed.connect(self._on_smart_failed)
        self._smart_loader.start()

    def _open_settings(self):
        dlg = SettingsDialog(self.settings, self)
        if dlg.exec():
            self.poller.set_interval(
                self.settings.get("polling", "full_interval_sec", 300),
                self.settings.get("polling", "quick_interval_sec", 30))
            self.db.cleanup(int(self.settings.get("history", "retention_days", 90)))
            # Theme may have changed via the dialog too.
            new_theme = theme.normalize(self.settings.get("general", "theme", "light"))
            if new_theme != self._theme:
                self._theme = new_theme
                theme.apply_theme(QApplication.instance(), self._theme)
                self._sync_theme_action()
            self._set_status("Settings saved.")

    def _about(self):
        QMessageBox.about(
            self, "About DiskMaster",
            "<b>DiskMaster</b><br>"
            "HDD/SSD/NVMe monitoring for Linux.<br>"
            "Backend: HDSentinel + smartctl + sysfs + nvme-cli.<br><br>"
            f"Privilege method: <b>{self.service.client.method}</b>")

    # --------------------------------------------------------------- signals --

    def _populate(self, disks: list[DiskInfo]):
        self._disks = {d.device: d for d in disks}
        self.disk_panel.set_disks(disks)  # auto-selects → _on_select_device

    def _refresh_volumes(self):
        self.volume_panel.set_volumes(
            self.service.volumes(), self.disk_panel.disk_index())

    def _on_disks_updated(self, disks: list[DiskInfo]):
        self._populate(disks)
        self._refresh_volumes()
        self.priv_label.setText(f"priv: {self.service.client.method}")

        self.db.record_disks(disks)
        new_alerts = self.notifier.check(disks)
        for alert in new_alerts:
            self.db.add_alert(alert.identity, alert.alert_type, alert.message)
            self.notifier.notify([alert])
        if new_alerts:
            self.alert_log.reload()
        self._refresh_tray()
        self._stamp_updated()

    def _on_quick_updated(self, rows: dict):
        touched = []
        for device, row in rows.items():
            disk = self._disks.get(device)
            if not disk:
                continue
            if row.temp_current >= 0:
                disk.temp_current = row.temp_current
            if row.health >= 0:
                disk.health = row.health
            if row.power_on_hours >= 0:
                disk.power_on_hours = row.power_on_hours
            self.disk_panel.update_disk(disk)
            touched.append(disk)
        if not touched:
            return

        # Refresh the open tabs if the selected disk changed (skip Performance —
        # it samples live on its own timer).
        cur = self.disk_panel.current
        if cur and self._disks.get(cur) in touched:
            self._apply_to_tabs(self._disks[cur], include_perf=False)

        self.db.record_disks(touched)
        new_alerts = self.notifier.check(touched)
        for alert in new_alerts:
            self.db.add_alert(alert.identity, alert.alert_type, alert.message)
            self.notifier.notify([alert])
        if new_alerts:
            self.alert_log.reload()
        self._refresh_tray()
        self._stamp_updated()

    def _on_select_device(self, device: str):
        disk = self._disks.get(device)
        if disk:
            self._apply_to_tabs(disk, include_perf=True)
            self._update_overview_tab_icon(disk)

    def _apply_to_tabs(self, disk: DiskInfo, include_perf: bool):
        self.overview.set_disk(disk)
        self.temperature.set_disk(disk)
        self.information.set_disk(disk)
        self.log_panel.set_device(disk.device)
        if include_perf:
            self.performance.set_disk(disk)

    def _update_overview_tab_icon(self, disk: DiskInfo):
        self.tabs.setTabIcon(0, status_icon(disk.status, 14))

    def _on_poll_error(self, msg: str):
        self._set_status(f"⚠ {msg}")

    def _on_smart_loaded(self, device: str, attrs):
        self.smart_table.set_attributes(attrs)
        self.btn_load_smart.setEnabled(True)
        self.btn_load_smart.setText("Reload SMART data")
        self._set_status(f"SMART loaded for {device} ({len(attrs)} attributes)")
        disk = self._disks.get(device)
        if disk and attrs:
            self.db.record_smart(disk.identity, attrs)

    def _on_smart_failed(self, device: str, err: str):
        self.btn_load_smart.setEnabled(True)
        self.btn_load_smart.setText("Load SMART data")
        QMessageBox.warning(self, "SMART error", f"{device}:\n{err}")

    def _set_status(self, text: str):
        self.status_label.setText(text)

    def _stamp_updated(self):
        now = datetime.now().strftime("%d/%m/%Y %A %H:%M:%S")
        self._set_status(f"Status last updated: {now}")

    # ----------------------------------------------------------------- close --

    def closeEvent(self, event):
        self.poller.stop()
        self.poller.wait(3000)
        self.service.close()
        self.db.close()
        super().closeEvent(event)
