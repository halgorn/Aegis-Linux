"""Performance page — top processes + kernel tunables."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from aegis.collectors import procfs as proc_col
from aegis.collectors import sysfs as sysfs_col
from aegis.ui.theme import fmt_bytes
from aegis.ui.widgets.qt import make_section, make_title
from aegis.ui.pages.qt._helpers import (
    _bridge, _runner, _run_scan, _wire_bridge,
)


class PerformancePage(QWidget):
    def __init__(self, host: QWidget) -> None:
        super().__init__()
        self._pending: list = []
        self._runner = _runner(host)
        self._bridge = _bridge(host)
        _wire_bridge(self)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)
        outer.addWidget(make_title("Performance",
            "Top processes and tunable kernel parameters."))
        outer.addWidget(make_section("Top processes (by CPU)"))
        self._tbl = QTableWidget(0, 5)
        self._tbl.setHorizontalHeaderLabels(["PID", "Name", "CPU %", "RSS", "User"])
        self._tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setAlternatingRowColors(True)
        outer.addWidget(self._tbl, 1)
        outer.addWidget(make_section("Tunables"))
        self._tun_info: dict[str, QLabel] = {}
        tun_w = QWidget(); tun_l = QFormLayout(tun_w)
        for k in ("vm.swappiness", "vm.dirty_ratio", "vm.dirty_background_ratio"):
            lbl = QLabel("-"); tun_l.addRow(QLabel(k), lbl)
            self._tun_info[k] = lbl
        outer.addWidget(tun_w)

    def on_show(self) -> None:
        self._refresh()

    def _track(self, spec):
        self._pending.append(spec)

    def _untrack(self, spec):
        try:
            self._pending.remove(spec)
        except ValueError:
            pass

    def cancel_pending(self) -> None:
        for spec in list(self._pending):
            spec.cancel()
        self._pending.clear()

    def _refresh(self) -> None:
        _run_scan(self, runner=self._runner, bridge=self._bridge,
                  name="perf-sample",
                  fn=lambda: (proc_col.list_processes(top=30),
                              {k: sysfs_col.read_sysctl(k, "?") for k in self._tun_info}),
                  on_render=self._render)

    def _render(self, payload) -> None:
        procs, sysctl = payload
        self._tbl.setRowCount(len(procs))
        for i, p in enumerate(procs):
            self._tbl.setItem(i, 0, QTableWidgetItem(str(p.pid)))
            self._tbl.setItem(i, 1, QTableWidgetItem(p.name[:30]))
            self._tbl.setItem(i, 2, QTableWidgetItem(f"{p.cpu_pct:.1f}"))
            self._tbl.setItem(i, 3, QTableWidgetItem(fmt_bytes(p.rss)))
            self._tbl.setItem(i, 4, QTableWidgetItem((p.user or "")[:20]))
        for k, v in sysctl.items():
            if k in self._tun_info:
                self._tun_info[k].setText(str(v))