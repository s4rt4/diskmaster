"""Main application window."""
from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
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

from .alert_log import AlertLogPanel
from .dashboard import DashboardPanel
from .history_chart import HistoryChart
from .selftest_panel import SelfTestPanel
from .settings_dialog import SettingsDialog
from .smart_table import SmartTable
from .tools_panel import ToolsPanel


class _SmartLoader(QThread):
    """One-shot SMART fetch off the GUI thread."""
    loaded = pyqtSignal(str, object)   # device, list[SmartAttribute]
    failed = pyqtSignal(str, str)      # device, error

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

        self.setWindowTitle("DiskMaster")
        if icon:
            self.setWindowIcon(icon)
        self.resize(960, 640)

        self._build_toolbar()
        self._build_central()
        self._build_statusbar()

        # Poller
        full = self.settings.get("polling", "full_interval_sec", 300)
        quick = self.settings.get("polling", "quick_interval_sec", 30)
        self.poller = PollerWorker(self.service, full, quick)
        self.poller.disks_updated.connect(self._on_disks_updated)
        self.poller.quick_updated.connect(self._on_quick_updated)
        self.poller.error.connect(self._on_poll_error)
        self.poller.status.connect(self._set_status)

        # Show sysfs disks immediately (no privilege needed).
        self._populate(self.service.sysfs_disks())
        self._set_status("Ready — click “Scan” to read health (requires admin).")

    # ----------------------------------------------------------- UI building --

    def _build_toolbar(self):
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        self.act_scan = QAction("⟳  Scan (admin)", self)
        self.act_scan.triggered.connect(self._start_scan)
        tb.addAction(self.act_scan)
        tb.addSeparator()
        act_settings = QAction("Settings", self)
        act_settings.triggered.connect(self._open_settings)
        tb.addAction(act_settings)
        act_about = QAction("About", self)
        act_about.triggered.connect(self._about)
        tb.addAction(act_about)

    def _build_central(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: disk list
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(8, 8, 8, 8)
        lbl = QLabel("Disks")
        lbl.setStyleSheet("font-weight:bold; padding:4px;")
        self.disk_list = QListWidget()
        self.disk_list.currentItemChanged.connect(self._on_select)
        lv.addWidget(lbl)
        lv.addWidget(self.disk_list)

        # Right: tabs
        self.tabs = QTabWidget()
        self.dashboard = DashboardPanel()
        self.tabs.addTab(self.dashboard, "Overview")

        smart_tab = QWidget()
        sv = QVBoxLayout(smart_tab)
        self.btn_load_smart = QPushButton("Load SMART data")
        self.btn_load_smart.clicked.connect(self._load_smart)
        self.smart_table = SmartTable()
        sv.addWidget(self.btn_load_smart)
        sv.addWidget(self.smart_table)
        self.tabs.addTab(smart_tab, "SMART")

        self.history_chart = HistoryChart(self.db)
        self.tabs.addTab(self.history_chart, "History")

        self.selftest_panel = SelfTestPanel(self.service)
        self.tabs.addTab(self.selftest_panel, "Self-Test")

        self.tools_panel = ToolsPanel(self.service)
        self.tabs.addTab(self.tools_panel, "Tools")

        self.alert_log = AlertLogPanel(self.db)
        self.tabs.addTab(self.alert_log, "Alerts")

        splitter.addWidget(left)
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 720])
        self.setCentralWidget(splitter)

    def _build_statusbar(self):
        self.status_label = QLabel("")
        self.statusBar().addWidget(self.status_label)
        self.priv_label = QLabel("")
        self.statusBar().addPermanentWidget(self.priv_label)

    # --------------------------------------------------------------- tray ----

    def set_tray(self, tray):
        """Hold the tray icon: refresh its tooltip on every poll and use its
        bubble as the desktop-notification fallback."""
        self._tray = tray
        self.notifier.set_tray_callback(
            lambda title, msg: tray.showMessage(
                title, msg,
                QSystemTrayIcon.MessageIcon.Warning, 8000))

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
        item = self.disk_list.currentItem()
        if not item:
            return
        device = item.data(Qt.ItemDataRole.UserRole)
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
            self._set_status("Settings saved.")

    def _about(self):
        QMessageBox.about(
            self,
            "About DiskMaster",
            "<b>DiskMaster</b><br>"
            "HDD/SSD/NVMe monitoring for Linux.<br>"
            "Backend: HDSentinel + smartctl + sysfs + nvme-cli.<br><br>"
            f"Privilege method: <b>{self.service.client.method}</b>",
        )

    # --------------------------------------------------------------- signals --

    def _populate(self, disks: list[DiskInfo]):
        prev = None
        item = self.disk_list.currentItem()
        if item:
            prev = item.data(Qt.ItemDataRole.UserRole)

        self.disk_list.blockSignals(True)
        self.disk_list.clear()
        self._disks = {d.device: d for d in disks}
        select_row = 0
        for i, d in enumerate(disks):
            label = f"{d.device}\n{d.model or d.disk_type.value} · {d.size_human}"
            it = QListWidgetItem(label)
            it.setData(Qt.ItemDataRole.UserRole, d.device)
            self.disk_list.addItem(it)
            if d.device == prev:
                select_row = i
        self.disk_list.blockSignals(False)
        if self.disk_list.count():
            self.disk_list.setCurrentRow(select_row)

    def _on_disks_updated(self, disks: list[DiskInfo]):
        self._populate(disks)
        self.priv_label.setText(f"priv: {self.service.client.method}")

        # Persist history and fire any new threshold alerts.
        self.db.record_disks(disks)
        new_alerts = self.notifier.check(disks)
        for alert in new_alerts:
            self.db.add_alert(alert.identity, alert.alert_type, alert.message)
            self.notifier.notify([alert])

        self.history_chart.reload()
        self._refresh_tray()
        if new_alerts:
            self.alert_log.reload()

    def _on_quick_updated(self, rows: dict):
        """Patch temp/health/POH from a lightweight -solid poll, without losing
        the richer fields (status, serial, SMART) from the last full scan."""
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
            touched.append(disk)

        if not touched:
            return

        # Refresh the dashboard if the selected disk changed.
        item = self.disk_list.currentItem()
        if item:
            sel = self._disks.get(item.data(Qt.ItemDataRole.UserRole))
            if sel in touched:
                self.dashboard.set_disk(sel)

        self.db.record_disks(touched)
        new_alerts = self.notifier.check(touched)
        for alert in new_alerts:
            self.db.add_alert(alert.identity, alert.alert_type, alert.message)
            self.notifier.notify([alert])
        self.history_chart.reload()
        self._refresh_tray()
        if new_alerts:
            self.alert_log.reload()

    def _on_select(self, current: QListWidgetItem, _prev=None):
        if not current:
            self.dashboard.clear()
            self.history_chart.set_identity(None)
            self.selftest_panel.set_device(None)
            self.tools_panel.set_disk(None)
            return
        device = current.data(Qt.ItemDataRole.UserRole)
        disk = self._disks.get(device)
        if disk:
            self.dashboard.set_disk(disk)
            self.history_chart.set_identity(disk.identity)
            self.selftest_panel.set_device(disk.device)
            self.tools_panel.set_disk(disk)

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

    # ----------------------------------------------------------------- close --

    def closeEvent(self, event):
        self.poller.stop()
        self.poller.wait(3000)
        self.service.close()
        self.db.close()
        super().closeEvent(event)
