"""Dashboard page — KPI overview + quick actions + system info."""
from __future__ import annotations

import os
import socket
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QSplitter, QVBoxLayout, QWidget,
)

from aegis.services import backup_service as backup_svc
from aegis.ui.theme import fmt_bytes
from aegis.ui.widgets.qt import (
    CancellableScanMixin, make_kpi, make_section, make_title, set_kpi_value,
)
from aegis.ui.pages.qt._helpers import (
    _bridge, _log, _runner, _run_scan, _show_toast, _wire_bridge, dashboard_snapshot,
)


class DashboardPage(QWidget, CancellableScanMixin):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        CancellableScanMixin.__init__(self)
        self._runner = _runner(host)
        self._bridge = _bridge(host)
        _wire_bridge(self)
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._refresh)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(14)
        hour = datetime.now().hour
        greet = ("Good morning" if hour < 12
                 else "Good afternoon" if hour < 18
                 else "Good evening")
        user = os.environ.get("USER") or os.environ.get("USERNAME") or "user"
        host_name = socket.gethostname()
        outer.addWidget(make_title(
            f"{greet}, {user}",
            f"Welcome to Aegis Linux on {host_name}. Here's an overview of your system.",
        ))
        self._kpi_cpu = make_kpi("CPU", "—", "blue")
        self._kpi_ram = make_kpi("Memory", "—", "mauve")
        self._kpi_disk = make_kpi("Disk", "—", "green")
        self._kpi_uptime = make_kpi("Uptime", "—", "cyan")
        grid = QGridLayout(); grid.setSpacing(12)
        grid.addWidget(self._kpi_cpu, 0, 0)
        grid.addWidget(self._kpi_ram, 0, 1)
        grid.addWidget(self._kpi_disk, 0, 2)
        grid.addWidget(self._kpi_uptime, 0, 3)
        gw = QWidget(); gw.setLayout(grid)
        outer.addWidget(gw)
        outer.addWidget(make_section("System"))
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        info = QFrame(); info.setObjectName("card")
        il = QVBoxLayout(info)
        il.setContentsMargins(16, 14, 16, 14)
        il.setSpacing(6)
        self._info_lines: dict[str, QLabel] = {}
        for k in ("Distro", "Kernel", "Python", "CPU Model",
                  "CPU Cores", "Total RAM", "Total Disk"):
            row = QHBoxLayout()
            lk = QLabel(k); lk.setObjectName("kpi_label"); lk.setFixedWidth(120)
            lv = QLabel("—")
            row.addWidget(lk); row.addWidget(lv, 1)
            rw = QWidget(); rw.setLayout(row)
            il.addWidget(rw)
            self._info_lines[k] = lv
        split.addWidget(info)
        qa = QFrame(); qa.setObjectName("card")
        ql = QVBoxLayout(qa); ql.setContentsMargins(16, 14, 16, 14); ql.setSpacing(8)
        ql.addWidget(QLabel("Quick actions"))
        for label, fn in (
            ("Run health scan", lambda: self._navigate("health")),
            ("Open cleaner", lambda: self._navigate("cleaner")),
            ("Open monitor", lambda: self._navigate("monitor")),
            ("Backup now", self._backup_now),
        ):
            b = QPushButton(label); b.clicked.connect(fn); ql.addWidget(b)
        ql.addStretch()
        split.addWidget(qa)
        split.setSizes([640, 320])
        outer.addWidget(split, 1)

    def _navigate(self, key: str) -> None:
        win = self.window()
        if hasattr(win, "show_page"):
            win.show_page(key)

    def _backup_now(self) -> None:
        try:
            entry = backup_svc.snapshot_files(
                [str(Path.home() / ".bashrc"), str(Path.home() / ".profile")],
                reason="manual-dashboard",
            )
            _show_toast(self, f"Backup #{entry.id} created.", "success")
        except Exception as e:  # noqa: BLE001
            _show_toast(self, f"Backup failed: {e}", "error")

    def _refresh(self) -> None:
        _run_scan(self, runner=self._runner, bridge=self._bridge,
                  name="dashboard-snapshot",
                  fn=dashboard_snapshot,
                  on_render=self._render)

    def _render(self, snap: dict) -> None:
        try:
            set_kpi_value(self._kpi_cpu, snap['cpu_pct'], fmt="{:.0f}", suffix="%")
            self._kpi_ram._value_lbl.setText(  # type: ignore[attr-defined]
                f"{snap['ram_pct']:.0f}% · {fmt_bytes(snap['ram_used'])}"
            )
            self._kpi_disk._value_lbl.setText(  # type: ignore[attr-defined]
                f"{snap['disk_pct']:.0f}% · {fmt_bytes(snap['disk_used'])}"
            )
            self._kpi_uptime._value_lbl.setText(snap['uptime'])  # type: ignore[attr-defined]
            mapping = {
                "Distro": snap.get("distro"),
                "Kernel": snap.get("kernel"),
                "Python": snap.get("python"),
                "CPU Model": snap.get("cpu_model"),
                "CPU Cores": snap.get("cpu_cores"),
                "Total RAM": fmt_bytes(snap.get("ram_total", 0)),
                "Total Disk": fmt_bytes(snap.get("disk_total", 0)),
            }
            for k, v in mapping.items():
                if k in self._info_lines and v is not None:
                    self._info_lines[k].setText(str(v))
        except Exception as e:  # noqa: BLE001
            _log.warning("dashboard render failed: %s", e)

    def on_show(self) -> None:
        self._refresh()
        self._timer.start()

    def on_hide(self) -> None:
        self._timer.stop()