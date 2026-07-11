"""Drivers page — kernel modules currently loaded."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from aegis.services.drivers_service import scan as scan_drivers
from aegis.ui.widgets.qt import make_title
from aegis.ui.pages.qt._helpers import (
    _bridge, _runner, _run_scan, _wire_bridge,
)


class DriversPage(QWidget):
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
        outer.addWidget(make_title("Drivers", "Kernel modules currently loaded."))
        self._tbl = QTableWidget(0, 4)
        self._tbl.setHorizontalHeaderLabels(["Module", "Size", "Used by", "State"])
        self._tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._tbl.verticalHeader().setVisible(False)
        outer.addWidget(self._tbl, 1)

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
                  name="drv-scan", fn=scan_drivers, on_render=self._render)

    def _render(self, r) -> None:
        mods = r.modules
        self._tbl.setRowCount(len(mods))
        for i, m in enumerate(mods):
            self._tbl.setItem(i, 0, QTableWidgetItem(m["name"]))
            self._tbl.setItem(i, 1, QTableWidgetItem(m["size"]))
            self._tbl.setItem(i, 2, QTableWidgetItem(m["used_by"]))
            self._tbl.setItem(i, 3, QTableWidgetItem(m["state"]))