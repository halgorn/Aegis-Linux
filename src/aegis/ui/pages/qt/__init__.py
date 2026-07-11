"""Qt page registry and per-page modules.

Each page lives in its own file (≤ 500 LOC each) and is re-exported
here so ``MainWindow`` can build them by name.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QWidget

from aegis.ui.pages.qt._helpers import (
    _bridge, _make_chart, _read_os_release, _runner, _run_scan,
    _set_status, _show_toast, _wire_bridge, dashboard_snapshot,
)
from aegis.ui.pages.qt.cleaner import CleanerPage
from aegis.ui.pages.qt.dashboard import DashboardPage
from aegis.ui.pages.qt.disks import DisksPage
from aegis.ui.pages.qt.drivers import DriversPage
from aegis.ui.pages.qt.health import HealthPage
from aegis.ui.pages.qt.logs import LogsPage
from aegis.ui.pages.qt.monitor import MonitorPage
from aegis.ui.pages.qt.network import NetworkPage
from aegis.ui.pages.qt.packages import PackagesPage
from aegis.ui.pages.qt.performance import PerformancePage
from aegis.ui.pages.qt.restore import RestorePage
from aegis.ui.pages.qt.security import SecurityPage
from aegis.ui.pages.qt.settings import SettingsPage
from aegis.ui.pages.qt.startup import StartupPage

__all__ = [
    "CleanerPage", "DashboardPage", "DisksPage", "DriversPage", "HealthPage",
    "LogsPage", "MonitorPage", "NetworkPage", "PackagesPage", "PerformancePage",
    "RestorePage", "SecurityPage", "SettingsPage", "StartupPage",
    "build_pages",
]


def build_pages(host: QWidget) -> dict[str, QWidget]:
    return {
        "dashboard": DashboardPage(host),
        "cleaner": CleanerPage(host),
        "monitor": MonitorPage(host),
        "performance": PerformancePage(host),
        "health": HealthPage(host),
        "security": SecurityPage(host),
        "network": NetworkPage(host),
        "disks": DisksPage(host),
        "drivers": DriversPage(host),
        "packages": PackagesPage(host),
        "startup": StartupPage(host),
        "restore": RestorePage(host),
        "logs": LogsPage(host),
        "settings": SettingsPage(host),
    }