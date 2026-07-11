"""Startup page — enabled systemd services."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from aegis.services.startup_service import scan as scan_startup
from aegis.ui.widgets.qt import make_title
from aegis.ui.pages.qt._helpers import (
    _bridge, _runner, _run_scan, _wire_bridge,
)


class StartupPage(QWidget):
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
        outer.addWidget(make_title("Startup", "Enabled systemd services."))
        self._tbl = QTableWidget(0, 4)
        self._tbl.setHorizontalHeaderLabels(["Name", "Scope", "State", "Description"])
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
                  name="startup-scan", fn=scan_startup, on_render=self._render)

    def _render(self, r) -> None:
        items = r.items
        self._tbl.setRowCount(len(items))
        for i, it in enumerate(items):
            self._tbl.setItem(i, 0, QTableWidgetItem(it["name"]))
            self._tbl.setItem(i, 1, QTableWidgetItem(it["scope"]))
            self._tbl.setItem(i, 2, QTableWidgetItem(it["state"]))
            self._tbl.setItem(i, 3, QTableWidgetItem((it.get("description") or "")[:100]))